"use client"

// E8.1 — the MLB dynasty PROSPECT BOARD, and its DISAGREEMENT view.
//
// One component, two surfaces (`view="board" | "disagreements"`): the disagreement view is the same
// board filtered to the rows where our translated line and the scouts' grade rank a player
// differently, which is the differentiated read — the MLB analog of the NFL fade view.
//
// 🔒 HONEST FRAME (`best_alpha = 0`), and it is POSITION-DIFFERENTIATED, which is the actual product:
//
//   * ARMS → LEAD WITH FV. Scouting grades add real, gate-clearing lift ON TOP of our line for
//     pitchers (E7.8), and pitcher stats translate materially worse than batter stats (K% OOS corr
//     0.37 vs 0.64) — that gap is the room a scouting grade fills.
//   * BATS → LEAD WITH OUR LINE + age-relative-to-level. FV is largely redundant with our read for
//     hitters (no batter stage cleared the deflated gates); it is CONFIRMATION.
//
// So the claim is "we know WHEN to trust the scouts" — never "we beat FanGraphs". `leadWith` below
// is that verdict expressed as column order, so the page physically reads the way the evidence says
// it should rather than carrying the caveat only in prose.
//
// ⚠️ THE FRAMING COPY IS NOT AUTHORED HERE. It arrives in the manifest's `framing` block, written by
// `export_prospect_board_json.FRAMING`, so the wording travels with the model that earned it. This
// file renders it; it must not paraphrase it. The one thing hard-coded here is a FALLBACK for a
// pre-E8.1 payload that carries no framing at all — and the fallback is a caveat, never a claim.

import { Fragment, useEffect, useId, useMemo, useState } from "react"
import { ChevronDown, ChevronRight, Search } from "lucide-react"
import {
  ALL_ROWS,
  EmptyBlock,
  InfoTip,
  LoadingBlock,
  Pagination,
  SurfaceHeader,
} from "@/components/fantasy/shared"
import { Picker } from "@/components/ui/picker"
import {
  useProspectBoard,
  useProspectLeague,
  useProspectManifest,
} from "@/lib/fantasy-queries"
import {
  PROSPECT_SEASON,
  dec3,
  isBatter,
  isDisagreement,
  numOrDash,
  pct,
} from "@/lib/mlb-prospects"
import type { Prospect, ProspectFraming } from "@/lib/mlb-prospects"

type View = "board" | "disagreements"
type TypeTab = "all" | "batter" | "pitcher"
type SortKey = "rank" | "fv" | "mleScore" | "modelScore" | "age" | "eta" | "disagreement" | "compFpMedian"

const TYPE_TABS: { value: TypeTab; label: string }[] = [
  { value: "all", label: "All" },
  { value: "batter", label: "Hitters" },
  { value: "pitcher", label: "Pitchers" },
]

// ⭐ E7.8's verdict, as column order. "all" keeps the board's own blended order and says so.
const leadWith = (tab: TypeTab): "fv" | "model" | "board" =>
  tab === "pitcher" ? "fv" : tab === "batter" ? "model" : "board"

/** The one piece of copy this file owns: what to say when a payload carries no framing block at
 *  all (a board exported before E8.1). It is deliberately a CAVEAT — if we cannot render the
 *  measured framing, we must not invent a confident one in its place. */
const FRAMING_FALLBACK =
  "FanGraphs + MLB Pipeline consensus, our independent MLE-translated line, and where they " +
  "disagree. No edge or win-rate claim is made or implied, and nothing here claims to beat " +
  "FanGraphs."

// ── small presentational pieces ───────────────────────────────────────────────────────────────

function Chip({ children, tone = "gray" }: { children: React.ReactNode; tone?: string }) {
  const tones: Record<string, string> = {
    gray: "text-gray-400 bg-gray-500/10 border-gray-500/30",
    green: "text-emerald-400 bg-emerald-500/10 border-emerald-500/30",
    amber: "text-amber-400 bg-amber-500/10 border-amber-500/30",
    sky: "text-sky-400 bg-sky-500/10 border-sky-500/30",
    rose: "text-rose-400 bg-rose-500/10 border-rose-500/30",
  }
  return (
    <span className={`inline-flex items-center rounded border px-1.5 py-0.5 text-[10px] font-medium ${tones[tone] ?? tones.gray}`}>
      {children}
    </span>
  )
}

/** A projected rate with its uncertainty attached, and its CONFIDENCE made visible.
 *
 *  🚨 The `weak` styling is load-bearing, not decoration. E7.3 measured ISO at OOS corr 0.43 and
 *  pitcher K%/BB% at ~0.37 against batter K% at 0.64 — presenting all of them in identical type
 *  would invite a reader to trust them equally, which the measurement says they should not. And the
 *  ± is PARAMETER uncertainty: it ranks confidence correctly but is too tight to read as a
 *  calibrated interval, which the standing note beneath the table states outright. */
function RateCell({
  value,
  sd,
  weak = false,
  fmt = pct,
}: {
  value?: number
  sd?: number
  weak?: boolean
  fmt?: (v: number | null | undefined, nd?: number) => string
}) {
  if (value == null) return <span className="text-[11px] text-gray-700">—</span>
  return (
    <div className="leading-tight">
      <div className={weak ? "text-xs text-gray-400" : "text-xs font-medium text-gray-200"}>
        {fmt(value)}
      </div>
      {sd != null && <div className="text-[10px] text-gray-600">±{fmt(sd)}</div>}
    </div>
  )
}

/** Where the comps' outcomes landed, as four proportional segments. The BUST share leads and is the
 *  widest thing on most rows — that is the honest downside E7.13 exists to show, so it is drawn
 *  first rather than tucked behind the median. */
function CompOutcomeBar({ p }: { p: Prospect }) {
  const seg = [
    { n: p.compNNever ?? 0, cls: "bg-gray-700", label: "never reached MLB" },
    { n: p.compNFringe ?? 0, cls: "bg-sky-900", label: "fringe" },
    { n: p.compNRegular ?? 0, cls: "bg-sky-600", label: "regular" },
    { n: p.compNImpact ?? 0, cls: "bg-emerald-500", label: "impact" },
  ]
  const total = seg.reduce((s, x) => s + x.n, 0)
  if (!total) return <span className="text-[11px] text-gray-700">—</span>
  return (
    <div className="flex h-1.5 w-full overflow-hidden rounded-full bg-[#1a1a1a]" title={seg.map((s) => `${s.n} ${s.label}`).join(" · ")}>
      {seg.map((s) => (
        <div key={s.label} className={s.cls} style={{ width: `${(s.n / total) * 100}%` }} />
      ))}
    </div>
  )
}

/** The comp panel: who he looks like, and what those players ACTUALLY did.
 *
 *  ⚠️ E7.13's own finding is that the comp distribution is honest about DIFFERENCES between players
 *  and OPTIMISTIC about absolute LEVELS. So this panel shows the distribution and the bust share and
 *  never quotes a precision figure — "similar to X, Y, Z, and here is how that group turned out",
 *  not "we project N points". */
function CompPanel({ p, framing }: { p: Prospect; framing?: ProspectFraming }) {
  if (!p.compNames && p.compFpMedian == null) {
    return (
      <p className="text-xs text-gray-600">
        No historical comps for this profile — too little of his own record is observed for the
        neighbourhood to mean anything. Blank here is “we won’t guess”, not “no comparable players
        exist”.
      </p>
    )
  }
  const thin = p.compQuality === "thin"
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[11px] uppercase tracking-wide text-gray-500">Looks like</span>
        <Chip tone={thin ? "amber" : p.compQuality === "strong" ? "green" : "gray"}>
          {p.compQuality ?? "—"} match
        </Chip>
        {p.compRankDelta != null && p.compRankDelta !== 0 && (
          <Chip tone={p.compRankDelta > 0 ? "green" : "rose"}>
            comps moved him {p.compRankDelta > 0 ? "up" : "down"} {Math.abs(p.compRankDelta)}
          </Chip>
        )}
      </div>
      <p className="text-xs text-gray-300">{p.compNames5 ?? p.compNames}</p>
      {p.compNote && <p className="text-[11px] leading-relaxed text-gray-500">{p.compNote}</p>}
      <CompOutcomeBar p={p} />
      <div className="flex flex-wrap gap-x-5 gap-y-1 text-[11px] text-gray-500">
        {p.compBustRate != null && (
          <span>
            <span className="text-gray-300">{pct(p.compBustRate, 0)}</span> never reached MLB
          </span>
        )}
        {p.compFpMedian != null && (
          <span>
            median <span className="text-gray-300">{Math.round(p.compFpMedian).toLocaleString()}</span> dynasty pts
          </span>
        )}
        {p.compBandLo != null && p.compBandHi != null && (
          <span>
            {p.compBandQuantiles ?? "band"}{" "}
            <span className="text-gray-300">
              {Math.round(p.compBandLo).toLocaleString()}–{Math.round(p.compBandHi).toLocaleString()}
            </span>
          </span>
        )}
      </div>
      {thin && (
        <p className="text-[11px] text-amber-500/80">
          Thin match — read the band, not the median.
        </p>
      )}
      <p className="text-[11px] leading-relaxed text-gray-600">
        {framing?.comps ??
          "Historical prospects with a similar profile, and what they actually produced. The pool " +
            "deliberately includes the players who busted. This is a similarity estimate, not a projection."}
      </p>
    </div>
  )
}

/** The expanded row: our full line, the scouts' full view, the comps, and the blurb. */
function DetailPanel({ p, framing }: { p: Prospect; framing?: ProspectFraming }) {
  const bat = isBatter(p)
  return (
    <div className="grid gap-5 border-t border-[#1f1f1f] bg-[#0c0c0c] px-4 py-4 md:grid-cols-3">
      <div className="space-y-2">
        <p className="text-[11px] uppercase tracking-wide text-gray-500">Our translated line</p>
        {bat ? (
          <dl className="space-y-1 text-xs">
            <Row label="K%" value={pct(p.mleK)} sd={p.mleKSd} fmt={pct} note="strong" />
            <Row label="BB%" value={pct(p.mleBb)} sd={p.mleBbSd} fmt={pct} note="strong" />
            <Row label="ISO" value={dec3(p.mleIso)} sd={p.mleIsoSd} fmt={dec3} note="weak" />
            <Row label="Sample" value={p.mlePa != null ? `${p.mlePa} PA @ ${p.mleLevel ?? "—"}` : "—"} />
          </dl>
        ) : (
          <dl className="space-y-1 text-xs">
            <Row label="GB%" value={pct(p.mlePGb)} sd={p.mlePGbSd} fmt={pct} note="strong" />
            <Row label="K%" value={pct(p.mlePK)} sd={p.mlePKSd} fmt={pct} note="weak" />
            <Row label="BB%" value={pct(p.mlePBb)} sd={p.mlePBbSd} fmt={pct} note="weak" />
            <Row label="Sample" value={p.mlePTbf != null ? `${p.mlePTbf} TBF @ ${p.mlePLevel ?? "—"}` : "—"} />
          </dl>
        )}
        {p.mleK == null && p.mlePK == null && (
          <p className="text-[11px] leading-relaxed text-gray-600">
            No translated line yet — complex/DSL and just-drafted prospects have an identity but no
            minor-league record to translate. He stays on the board on the scouts’ grade alone
            rather than being dropped.
          </p>
        )}
        {p.speedFlag && (
          <p className="text-[11px] leading-relaxed text-amber-500/80">
            Plus speed — and stolen bases are invisible to us. Every metric we translate is a
            per-PA/per-TBF rate, so if your league scores SB we are under-rating him.
          </p>
        )}
      </div>

      <div className="space-y-2">
        <p className="text-[11px] uppercase tracking-wide text-gray-500">The scouts</p>
        <dl className="space-y-1 text-xs">
          <Row label="FanGraphs FV" value={p.fv != null ? String(p.fv) : "—"} />
          <Row label="Risk" value={p.risk ?? "—"} />
          <Row label="FG overall / org" value={`${p.fgOverallRank ?? "—"} / ${p.fgOrgRank ?? "—"}`} />
          <Row label="Pipeline overall / org" value={`${p.pipelineOverallRank ?? "—"} / ${p.pipelineOrgRank ?? "—"}`} />
          <Row label="Consensus" value={p.consensusRank != null ? `#${p.consensusRank} · ${p.consensusConfidence ?? ""}` : "—"} />
        </dl>
        {p.onFgBoard === false && (
          <p className="text-[11px] leading-relaxed text-gray-600">
            MLB Pipeline ranks him; FanGraphs’ board does not carry him at all — the loudest
            disagreement two sources can produce, so he is added as a row rather than dropped. His
            FanGraphs columns are blank because there is no FanGraphs row, not because he is ungraded.
          </p>
        )}
        {p.inMajors && (
          <p className="text-[11px] leading-relaxed text-gray-600">
            {framing?.inMajors ??
              "Already listed at MLB. Most minor-league dynasty drafts do not make these players draftable — check your league's rules."}
          </p>
        )}
      </div>

      <div className="space-y-2">
        <p className="text-[11px] uppercase tracking-wide text-gray-500">Historical comps</p>
        <CompPanel p={p} framing={framing} />
        {p.note && (
          <p className="mt-3 border-t border-[#1f1f1f] pt-2 text-[11px] leading-relaxed text-gray-500">
            {p.note}
          </p>
        )}
      </div>
    </div>
  )
}

function Row({
  label,
  value,
  sd,
  fmt,
  note,
}: {
  label: string
  value: string
  sd?: number
  fmt?: (v: number | null | undefined, nd?: number) => string
  note?: "strong" | "weak"
}) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="text-gray-500">
        {label}
        {note === "weak" && <span className="ml-1 text-[9px] uppercase text-amber-600/80">weak</span>}
      </dt>
      <dd className="text-gray-200">
        {value}
        {sd != null && fmt && <span className="ml-1 text-[10px] text-gray-600">±{fmt(sd)}</span>}
      </dd>
    </div>
  )
}

// ── the surface ───────────────────────────────────────────────────────────────────────────────

export function ProspectBoard({ view = "board" }: { view?: View }) {
  const manifestQ = useProspectManifest()
  const boardQ = useProspectBoard()
  const [league, setLeague] = useProspectLeague()
  const [tab, setTab] = useState<TypeTab>("all")
  const [org, setOrg] = useState("ALL")
  const [level, setLevel] = useState("ALL")
  const [eta, setEta] = useState("ALL")
  const [minorsOnly, setMinorsOnly] = useState(false)
  const [q, setQ] = useState("")
  const [sort, setSort] = useState<SortKey>(view === "disagreements" ? "disagreement" : "rank")
  const [desc, setDesc] = useState(true)
  const [page, setPage] = useState(0)
  const [pageSize, setPageSize] = useState<number>(50)
  const [open, setOpen] = useState<number | null>(null)
  const leagueId = useId()
  const orgId = useId()
  const levelId = useId()
  const etaId = useId()

  // ⚠️ Defensive read (NF-C0): a payload missing `players` must fall through to a VISIBLE empty
  // state, never render nothing. A 200 with an unexpected shape is the failure mode that produced a
  // dead-looking page with no error anywhere.
  const players: Prospect[] = boardQ.data?.players ?? []
  const manifest = manifestQ.data
  const framing = manifest?.framing
  const filters = manifest?.filters

  const rows = useMemo(() => {
    const needle = q.trim().toLowerCase()
    let out = players.filter((p) => {
      if (league !== "ALL" && p.league !== league) return false
      if (tab === "batter" && !isBatter(p)) return false
      if (tab === "pitcher" && isBatter(p)) return false
      if (org !== "ALL" && p.org !== org) return false
      if (level !== "ALL" && p.level !== level) return false
      if (eta !== "ALL" && String(p.eta ?? "") !== eta) return false
      if (minorsOnly && p.inMajors) return false
      if (needle && !p.name.toLowerCase().includes(needle)) return false
      return true
    })
    if (view === "disagreements") out = out.filter(isDisagreement)

    const key = sort
    const val = (p: Prospect): number | null => {
      switch (key) {
        case "rank":
          return p.rank
        case "fv":
          return p.fv ?? null
        case "mleScore":
          return p.mleScore ?? null
        case "modelScore":
          return p.modelScore ?? null
        case "age":
          return p.age ?? null
        case "eta":
          return p.eta ?? null
        case "disagreement":
          return p.disagreement ?? null
        case "compFpMedian":
          return p.compFpMedian ?? null
      }
    }
    // Rank sorts ASCENDING when "descending" is on — #1 is the top of the board, not the bottom.
    const flip = key === "rank" || key === "age" || key === "eta" ? -1 : 1
    return out.slice().sort((a, b) => {
      const av = val(a)
      const bv = val(b)
      // A missing value sorts LAST in either direction: an un-projected player must never win a
      // sort by being blank (the same rule the board's own scoring applies).
      if (av == null && bv == null) return a.rank - b.rank
      if (av == null) return 1
      if (bv == null) return -1
      return (desc ? 1 : -1) * flip * (bv - av)
    })
  }, [players, league, tab, org, level, eta, minorsOnly, q, view, sort, desc])

  const paged = useMemo(
    () => (pageSize === ALL_ROWS ? rows : rows.slice(page * pageSize, page * pageSize + pageSize)),
    [rows, page, pageSize],
  )

  useEffect(() => setPage(0), [league, tab, org, level, eta, minorsOnly, q, sort, desc])

  const lead = leadWith(tab)
  // #, Player, Age, ETA, FV, Our line, Our score, Disagree, Comps, chevron (+ Level unless FV leads)
  const colCount = lead === "fv" ? 10 : 11
  const isLoading = manifestQ.isLoading || boardQ.isLoading
  const failed = !isLoading && (boardQ.error || players.length === 0)

  const sortBtn = (key: SortKey, label: string, tip?: React.ReactNode) => (
    <button
      onClick={() => (sort === key ? setDesc((d) => !d) : (setSort(key), setDesc(true)))}
      className={`inline-flex items-center gap-0.5 ${sort === key ? "text-gray-200" : "text-gray-500 hover:text-gray-300"}`}
    >
      {tip ? <InfoTip label={label}>{tip}</InfoTip> : label}
      {sort === key && <span className="text-[9px]">{desc ? "▼" : "▲"}</span>}
    </button>
  )

  return (
    <div className="mx-auto max-w-7xl px-4 py-8">
      <SurfaceHeader
        title={view === "disagreements" ? "Where We Disagree" : "Dynasty Prospect Board"}
        blurb={
          view === "disagreements"
            ? "The prospects our translated minor-league line ranks differently than the scouts' grade does. This is the differentiated read — not a verdict, a conversation starter."
            : framing?.headline ?? FRAMING_FALLBACK
        }
      >
        <p className="mt-2 text-[11px] text-gray-600">
          {manifest?.season ?? PROSPECT_SEASON} board
          {manifest?.as_of_date ? ` · scouting snapshot ${manifest.as_of_date}` : ""}
          {manifest?.players ? ` · ${manifest.players.toLocaleString()} prospects` : ""}
          {manifest?.generated_at && !isNaN(new Date(manifest.generated_at).getTime())
            ? ` · built ${new Date(manifest.generated_at).toLocaleDateString()}`
            : ""}
        </p>
      </SurfaceHeader>

      {isLoading && <LoadingBlock label="Loading the prospect board…" />}

      {failed && (
        <EmptyBlock
          title="The prospect board isn't available yet"
          detail="This season's board hasn't been published to this surface yet. It's a build-time export, so it appears here once the board has been rebuilt and published."
        />
      )}

      {!isLoading && players.length > 0 && (
        <>
          {/* ── controls. ⭐ AL/NL leads because dynasty leagues are single-league: scoping the
              board to the one you actually draft in is the first thing a user does, and the choice
              is persisted so it survives a reload. ── */}
          <div className="mb-4 flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-1.5 text-xs">
              <label htmlFor={leagueId} className="text-gray-500">
                League
              </label>
              <Picker
                id={leagueId}
                value={league}
                onValueChange={setLeague}
                ariaLabel="American or National League"
                className="h-auto rounded border border-[#262626] bg-[#0f0f0f] px-2 py-1 text-base sm:text-xs text-gray-200 focus:border-[#10b981]"
                options={[
                  { value: "ALL", label: "Both" },
                  ...(filters?.leagues ?? ["AL", "NL"]).map((l) => ({ value: l, label: l })),
                ]}
              />
            </div>

            <div className="inline-flex overflow-hidden rounded border border-[#262626]">
              {TYPE_TABS.map((t) => (
                <button
                  key={t.value}
                  onClick={() => setTab(t.value)}
                  className={`px-2.5 py-1 text-xs transition-colors ${
                    tab === t.value ? "bg-[#1a1a1a] text-gray-100" : "text-gray-500 hover:text-gray-300"
                  }`}
                >
                  {t.label}
                </button>
              ))}
            </div>

            <FilterPicker id={orgId} label="Org" value={org} onChange={setOrg} options={filters?.orgs ?? []} />
            <FilterPicker id={levelId} label="Level" value={level} onChange={setLevel} options={filters?.levels ?? []} />
            <FilterPicker
              id={etaId}
              label="ETA"
              value={eta}
              onChange={setEta}
              options={(filters?.etas ?? []).map(String)}
            />

            <label className="flex items-center gap-1.5 text-xs text-gray-400">
              <input
                type="checkbox"
                checked={minorsOnly}
                onChange={(e) => setMinorsOnly(e.target.checked)}
                className="accent-[#10b981]"
              />
              Minors only
            </label>

            <div className="relative ml-auto">
              <Search className="absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-gray-600" />
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Search player"
                className="w-44 rounded border border-[#262626] bg-[#0f0f0f] py-1.5 pl-7 pr-2 text-base sm:text-xs text-gray-200 placeholder:text-gray-600 focus:border-[#10b981] focus:outline-none"
              />
            </div>
          </div>

          {/* ⭐ E7.8's asymmetry, stated where the reader is about to act on it. */}
          {tab !== "all" && (
            <p className="mb-3 rounded border border-[#1f2937] bg-[#0d1117] px-3 py-2 text-[11px] leading-relaxed text-gray-400">
              {framing?.byPosition?.[tab] ??
                (tab === "pitcher"
                  ? "For arms, lead with the scouts' grade — it adds real lift on top of our line, and pitcher stats translate materially worse than batter stats."
                  : "For bats, lead with our translated line and age relative to level — the scouts' grade is largely redundant with it here, so read FV as confirmation.")}
            </p>
          )}

          <div className="overflow-x-auto rounded-lg border border-[#262626]">
            <table className="w-full min-w-[900px] text-left">
              <thead className="border-b border-[#262626] bg-[#0f0f0f] text-[11px] uppercase tracking-wide text-gray-500">
                <tr>
                  <th className="px-3 py-2 font-medium">{sortBtn("rank", "#")}</th>
                  <th className="px-3 py-2 font-medium">Player</th>
                  {lead !== "fv" && <th className="px-3 py-2 font-medium">Level</th>}
                  <th className="px-3 py-2 font-medium">{sortBtn("age", "Age")}</th>
                  <th className="px-3 py-2 font-medium">{sortBtn("eta", "ETA")}</th>
                  {lead === "fv" ? (
                    <>
                      <th className="px-3 py-2 font-medium">{sortBtn("fv", "FV")}</th>
                      <th className="px-3 py-2 font-medium">Our line</th>
                    </>
                  ) : (
                    <>
                      <th className="px-3 py-2 font-medium">Our line</th>
                      <th className="px-3 py-2 font-medium">{sortBtn("fv", "FV")}</th>
                    </>
                  )}
                  <th className="px-3 py-2 font-medium">
                    {sortBtn(
                      "modelScore",
                      "Our score",
                      framing?.scoresAreWithinType ??
                        "A percentile among players of the SAME type — a hitter's 90 and a pitcher's 90 each mean 'elite among his own kind', not 'equally valuable'.",
                    )}
                  </th>
                  <th className="px-3 py-2 font-medium">
                    {sortBtn(
                      "disagreement",
                      "Disagree",
                      framing?.disagreement ??
                        "How much higher our score is than is usual for a player with that FV, in percentile points. A residual, not our score minus theirs.",
                    )}
                  </th>
                  <th className="px-3 py-2 font-medium">
                    {sortBtn(
                      "compFpMedian",
                      "Comps",
                      framing?.comps ??
                        "Similar historical prospects and what they actually produced. The pool includes the players who busted.",
                    )}
                  </th>
                  <th className="w-8 px-2 py-2" />
                </tr>
              </thead>
              <tbody className="divide-y divide-[#1a1a1a] text-sm">
                {paged.map((p) => {
                  const bat = isBatter(p)
                  const expanded = open === p.rank
                  return (
                    <Fragment key={p.rank}>
                      <tr
                        onClick={() => setOpen(expanded ? null : p.rank)}
                        className="cursor-pointer transition-colors hover:bg-[#0f0f0f]"
                      >
                        <td className="px-3 py-2 text-xs text-gray-500">
                          {p.rank}
                          {p.compRankDelta != null && p.compRankDelta !== 0 && (
                            <span
                              className={`ml-1 text-[9px] ${p.compRankDelta > 0 ? "text-emerald-500" : "text-rose-500"}`}
                              title={`Historical comps moved him ${Math.abs(p.compRankDelta)} places ${p.compRankDelta > 0 ? "up" : "down"}`}
                            >
                              {p.compRankDelta > 0 ? "▲" : "▼"}
                              {Math.abs(p.compRankDelta)}
                            </span>
                          )}
                        </td>
                        <td className="px-3 py-2">
                          <div className="font-medium text-gray-100">{p.name}</div>
                          <div className="flex flex-wrap items-center gap-1.5 text-[10px] text-gray-500">
                            <span>{p.org ?? "—"}</span>
                            <span className="text-gray-700">·</span>
                            <span>{p.pos ?? "—"}</span>
                            {p.inMajors && <Chip tone="amber">MLB — check eligibility</Chip>}
                            {p.speedFlag && <Chip tone="sky">SB blind spot</Chip>}
                            {p.onFgBoard === false && <Chip tone="gray">Pipeline only</Chip>}
                          </div>
                        </td>
                        {lead !== "fv" && (
                          <td className="px-3 py-2 text-xs text-gray-400">{p.level ?? "—"}</td>
                        )}
                        <td className="px-3 py-2 text-xs text-gray-300">
                          {numOrDash(p.age)}
                          {p.ageVsLevel != null && (
                            <span
                              className={`ml-1 text-[10px] ${p.ageVsLevel < 0 ? "text-emerald-500" : "text-gray-600"}`}
                              title="Age relative to the median age at his level — negative is young for the level"
                            >
                              {p.ageVsLevel > 0 ? "+" : ""}
                              {p.ageVsLevel.toFixed(1)}
                            </span>
                          )}
                        </td>
                        <td className="px-3 py-2 text-xs text-gray-400">{p.eta ?? "—"}</td>

                        {lead === "fv" ? (
                          <>
                            <FvCell p={p} />
                            <OurLineCell p={p} bat={bat} />
                          </>
                        ) : (
                          <>
                            <OurLineCell p={p} bat={bat} />
                            <FvCell p={p} />
                          </>
                        )}

                        <td className="px-3 py-2 text-xs text-gray-300">{numOrDash(p.modelScore, 0)}</td>
                        <td className="px-3 py-2">
                          {p.disagreement == null ? (
                            <span className="text-[11px] text-gray-700">—</span>
                          ) : (
                            <div className="leading-tight">
                              <div
                                className={`text-xs ${
                                  p.disagreementLabel === "WE'RE HIGHER"
                                    ? "text-emerald-400"
                                    : p.disagreementLabel === "SCOUTS HIGHER"
                                      ? "text-amber-400"
                                      : "text-gray-500"
                                }`}
                              >
                                {p.disagreement > 0 ? "+" : ""}
                                {p.disagreement.toFixed(0)}
                              </div>
                              {isDisagreement(p) && (
                                <div className="text-[9px] uppercase tracking-wide text-gray-600">
                                  {p.disagreementLabel === "WE'RE HIGHER" ? "we're higher" : "scouts higher"}
                                </div>
                              )}
                            </div>
                          )}
                        </td>
                        <td className="px-3 py-2 align-middle">
                          {p.compFpMedian == null ? (
                            <span className="text-[11px] text-gray-700">—</span>
                          ) : (
                            <div className="w-28 space-y-1">
                              <CompOutcomeBar p={p} />
                              <div className="text-[10px] text-gray-600">
                                {p.compBustRate != null ? `${pct(p.compBustRate, 0)} bust` : ""}
                                {p.compQuality === "thin" ? " · thin" : ""}
                              </div>
                            </div>
                          )}
                        </td>
                        <td className="px-2 py-2 text-gray-600">
                          {expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                        </td>
                      </tr>
                      {expanded && (
                        <tr>
                          {/* colSpan is DERIVED, not a literal: the Level column only renders when
                              our line leads (E7.8's asymmetry), so a hard-coded count silently
                              mis-spans the detail row on the Pitchers tab. */}
                          <td colSpan={colCount} className="p-0">
                            <DetailPanel p={p} framing={framing} />
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  )
                })}
              </tbody>
            </table>
          </div>

          <div className="mt-4">
            <Pagination
              page={page}
              pageSize={pageSize}
              total={rows.length}
              onPage={setPage}
              onPageSize={setPageSize}
            />
          </div>

          {rows.length === 0 && (
            <div className="mt-4">
              <EmptyBlock
                title="No prospects match these filters"
                detail={
                  view === "disagreements"
                    ? "Narrow filters plus the disagreement threshold can empty this view. Widen the league or org filter to see more."
                    : "Try widening the league, org or level filter."
                }
              />
            </div>
          )}

          {/* ── the standing honest note. Every string here is the EXPORTER's where one exists. ── */}
          <div className="mt-6 space-y-3 rounded-lg border border-[#262626] bg-[#0f0f0f] p-4 text-xs leading-relaxed text-gray-400">
            <p>
              <span className="font-semibold text-gray-300">What this is.</span>{" "}
              {framing?.headline ?? FRAMING_FALLBACK}
            </p>
            <p>
              <span className="font-semibold text-gray-300">What it is not.</span>{" "}
              {framing?.claim ??
                "This board makes no edge or win-rate claim and does not claim to beat FanGraphs."}
            </p>
            {framing?.uncertainty && <p>{framing.uncertainty}</p>}
            {framing?.scoresAreWithinType && <p>{framing.scoresAreWithinType}</p>}
            {(framing?.absences ?? []).map((a) => (
              <p key={a}>{a}</p>
            ))}
            {!framing && (
              <p>
                The ± beside each rate is parameter uncertainty on our projection: it ranks
                confidence correctly but is too tight to read as a calibrated interval. Treat a wide
                band as “we don’t know”, never as a priced range.
              </p>
            )}
          </div>
        </>
      )}
    </div>
  )
}

function FvCell({ p }: { p: Prospect }) {
  return (
    <td className="px-3 py-2">
      <div className="text-xs font-medium text-gray-200">{p.fv ?? "—"}</div>
      <div className="text-[10px] text-gray-600">
        {p.fgOverallRank ? `#${p.fgOverallRank}` : p.risk ?? ""}
      </div>
    </td>
  )
}

/** ⭐ The type-appropriate headline metrics, and only those. Batter K%/BB% and pitcher GB% are the
 *  measured-strong ones; ISO and pitcher K%/BB% are shown demoted. wOBA is absent and stays absent
 *  — it is a measured null (corr 0.22), not an oversight, and a future column must not resurrect it. */
function OurLineCell({ p, bat }: { p: Prospect; bat: boolean }) {
  return (
    <td className="px-3 py-2">
      <div className="flex items-center gap-3">
        {bat ? (
          <>
            <RateCell value={p.mleK} sd={p.mleKSd} />
            <RateCell value={p.mleBb} sd={p.mleBbSd} />
            <RateCell value={p.mleIso} sd={p.mleIsoSd} weak fmt={dec3} />
          </>
        ) : (
          <>
            <RateCell value={p.mlePGb} sd={p.mlePGbSd} />
            <RateCell value={p.mlePK} sd={p.mlePKSd} weak />
            <RateCell value={p.mlePBb} sd={p.mlePBbSd} weak />
          </>
        )}
      </div>
      <div className="mt-0.5 text-[9px] uppercase tracking-wide text-gray-700">
        {bat ? "K% · BB% · ISO" : "GB% · K% · BB%"}
      </div>
    </td>
  )
}

function FilterPicker({
  id,
  label,
  value,
  onChange,
  options,
}: {
  id: string
  label: string
  value: string
  onChange: (v: string) => void
  options: string[]
}) {
  if (options.length === 0) return null
  return (
    <div className="flex items-center gap-1.5 text-xs">
      <label htmlFor={id} className="text-gray-500">
        {label}
      </label>
      <Picker
        id={id}
        value={value}
        onValueChange={onChange}
        ariaLabel={label}
        className="h-auto rounded border border-[#262626] bg-[#0f0f0f] px-2 py-1 text-base sm:text-xs text-gray-200 focus:border-[#10b981]"
        options={[{ value: "ALL", label: "All" }, ...options.map((o) => ({ value: o, label: o }))]}
      />
    </div>
  )
}
