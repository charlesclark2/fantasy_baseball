"use client"

// NF3 — Season Projections (browse). The format-INDEPENDENT view: every projectable player's
// projected 2026 stat line, with the 80% range shown next to the point projection so the
// uncertainty is never hidden behind a single number.
//
// Deliberately NOT a ranking product: the fantasy-points column here is a REFERENCE scoring
// (standard nflverse std/half/PPR) used to order the table, and it says so. Your league's actual
// scoring lives on Rankings / League Board, which re-score this same raw line per format.

import { useId, useEffect, useMemo, useState } from "react"
import Link from "next/link"
import { Search } from "lucide-react"
import { useAuth } from "@/lib/auth-context"
import { canUse } from "@/lib/entitlements"
import { useFantasyProjections, useFullProjections, FANTASY_SEASON } from "@/lib/fantasy-queries"
import { fullSeasonRate, trimLockedTail } from "@/lib/fantasy"
import {
  EXPECTED_POINTS_LABEL,
  FORMAT_LOCK_SUFFIX,
  FULL_SEASON_RATE_LABEL,
  PROJECTED_GAMES_LABEL,
  REFERENCE_SCORING_LOCK_NOTE,
} from "@/lib/fantasy-claim-copy"
import {
  ALL_ROWS,
  ConfidenceBadge,
  EmptyBlock,
  FreemiumBoundary,
  GLOSSARY,
  InfoTip,
  IntervalBar,
  LockChip,
  LoadingBlock,
  MarketLeanNote,
  Pagination,
  PosBadge,
  RangeCell,
  PositionTabs,
  ProvenanceLine,
  RookieBadge,
  STAT_COLS,
  SUBSCRIBE_HREF,
  SurfaceHeader,
  UNCERTAINTY_HELP,
  UNCERTAINTY_LABEL,
  UncertaintyNote,
  UpgradeBanner,
  num,
  AvailabilityFlag,
  isStatWithheld,
  numOrLock,
  int,
  teamLabel,
  WeeklyDesignation,
  WithheldStat,
} from "@/components/fantasy/shared"
import { Picker } from "@/components/ui/picker"

type Scoring = "fpPpr" | "fpHalf" | "fpStd"
const SCORING_LABEL: Record<Scoring, string> = {
  fpPpr: "Full PPR",
  fpHalf: "Half PPR",
  fpStd: "Standard",
}

/** The one reference scoring a free caller may see — the same preset the free BOARD is scored at
 *  (`entitlement.FREE_BOARD_CONFIG`). Held as its own constant because this page's picker is not
 *  the board's format picker: it is scoring-INDEPENDENT data with a reference total laid over it,
 *  and conflating the two controls is how one of them ends up ungated. */
const FREE_SCORING: Scoring = "fpPpr"

export function ProjectionsTable() {
  // The PROJECTION is free for everyone — this page's rows, ranges and ADP are identical for every
  // caller. What entitlement decides here is which reference SCORING may be laid over it: full-PPR
  // is free, half-PPR and standard are the membership, matching the board's own format split.
  const { groups } = useAuth()
  const entitled = canUse("personalization", groups)
  const { data: publicData, isLoading, error } = useFantasyProjections()
  // 🔒 NF-EPIC 1 — the two paid reference scorings (`fpHalf`/`fpStd`) left the public payload on
  // 2026-08-10. `effScoring` below already pins an unentitled caller to full PPR, so this swap is
  // what makes that pinning REAL rather than a presentation choice: without the paid half fetched,
  // those columns simply do not exist in the data.
  const { data: fullData } = useFullProjections()
  const data = fullData ?? publicData
  const [pos, setPos] = useState("All")
  const [scoring, setScoring] = useState<Scoring>(FREE_SCORING)
  const [q, setQ] = useState("")
  const [rookiesOnly, setRookiesOnly] = useState(false)
  const [page, setPage] = useState(0)
  const [pageSize, setPageSize] = useState<number>(50)
  const scoringSelectId = useId()

  const locked = data?.locked === true

  // ⭐ THE SELECTION IS RE-DERIVED, NOT JUST DISABLED IN THE UI. Every read below goes through
  // `effScoring`, so an unentitled caller is on full-PPR no matter what the `scoring` STATE says —
  // a disabled `<option>` is a presentation detail and a state variable is not a gate (NF-C0e's
  // "wired ≠ invoked", pointed the other way: here the state is wired and must NOT be invoked).
  const effScoring: Scoring = entitled ? scoring : FREE_SCORING
  // E9.56b — on a LOCKED view, drop the undrafted tail: 632 of 858 rows carry no ADP and no value,
  // so they would render as a long alphabetical list of names and padlocks. The hidden count is
  // surfaced below the table, never silently swallowed.
  const { rows: players, hiddenCount } = useMemo(
    () => trimLockedTail(data?.players ?? []),
    [data],
  )

  // Rank is assigned on the position-filtered, scoring-sorted board and then CARRIED, so searching
  // (or filtering to rookies) narrows the rows WITHOUT renumbering them. A search that renumbers
  // hides the one thing you searched for — where the player actually sits on the board.
  const ranked = useMemo(() => {
    const scoped = players.filter((p) => (pos === "All" ? true : p.pos === pos))
    // ⚠️ E9.56b — DO NOT sort a locked view by a scoring column. On a locked row `fpPpr`/`fpHalf`/
    // `fpStd` are ABSENT, so the comparator below evaluates `-Infinity - -Infinity` = **NaN** on
    // every pair. `Array.sort` happens to treat a NaN comparator as 0 and leaves the order intact,
    // so this looks harmless — but it is undefined-behaviour-by-luck, and the order it accidentally
    // preserves is the one that matters: the server sorted locked rows onto market ADP precisely so
    // the array index cannot reconstruct our ranking (E9.56). Keep the server's order EXPLICITLY.
    const ordered = locked
      ? scoped
      : scoped.slice().sort((a, b) => (b[effScoring] ?? -Infinity) - (a[effScoring] ?? -Infinity))
    return ordered.map((p, i) => ({ player: p, rank: i + 1 }))
  }, [players, pos, effScoring, locked])

  const rows = useMemo(() => {
    const needle = q.trim().toLowerCase()
    return ranked
      .filter(({ player }) => (rookiesOnly ? player.rookie : true))
      .filter(({ player }) => (needle ? player.name.toLowerCase().includes(needle) : true))
  }, [ranked, q, rookiesOnly])

  const paged = useMemo(
    () => (pageSize === ALL_ROWS ? rows : rows.slice(page * pageSize, page * pageSize + pageSize)),
    [rows, page, pageSize],
  )

  useEffect(() => setPage(0), [pos, q, rookiesOnly, effScoring])

  // A shared interval domain across the visible rows, so bar widths are comparable down the column.
  const domain = useMemo(() => {
    let min = Infinity
    let max = -Infinity
    for (const { player } of paged) {
      if (player.fpP10 != null) min = Math.min(min, player.fpP10)
      if (player.fpP90 != null) max = Math.max(max, player.fpP90)
    }
    return Number.isFinite(min) && Number.isFinite(max) ? { min, max } : { min: 0, max: 1 }
  }, [paged])

  const statCols = STAT_COLS[pos] ?? []
  const hasAdp = useMemo(() => players.some((p) => p.adp != null), [players])

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      <SurfaceHeader
        title="Season Projections"
        blurb="Every projectable player's 2026 season line, with an 80% range on the fantasy-point total. This view is scoring-independent — it is the raw projected production your league's format is scored from."
      >
        <div className="mt-2">
          <ProvenanceLine
            season={data?.season ?? FANTASY_SEASON}
            generatedAt={data?.generated_at}
            extra={data?.base_season ? `built off ${data.base_season} production` : null}
            freshness={data?.freshness}
          />
        </div>
      </SurfaceHeader>

      {/* E9.56 — the server withheld this season's values from this caller. Rows still render with
          their public identity, each locked cell carrying its own chip; this is the page-level ask. */}
      {data?.locked && <UpgradeBanner season={data.season ?? FANTASY_SEASON} upgrade={data.upgrade} />}

      {isLoading && <LoadingBlock label="Loading projections…" />}

      {!isLoading && (error || players.length === 0) && (
        <EmptyBlock
          title="Projections aren't available yet"
          detail="The 2026 season projections haven't been published to this surface yet. Rankings and the League Board are built from the same model and are available now."
        />
      )}

      {!isLoading && players.length > 0 && (
        <>
          {/* controls */}
          <div className="mb-4 flex flex-wrap items-center gap-3">
            <PositionTabs value={pos} onChange={setPos} />
            <div className="relative">
              <Search className="absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-gray-600" />
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Search player"
                className="w-48 rounded border border-[#262626] bg-[#0f0f0f] py-1.5 pl-7 pr-2 text-base sm:text-xs text-gray-200 placeholder:text-gray-600 focus:border-[#10b981] focus:outline-none"
              />
            </div>
            <label className="flex items-center gap-1.5 text-xs text-gray-400">
              <input
                type="checkbox"
                checked={rookiesOnly}
                onChange={(e) => setRookiesOnly(e.target.checked)}
                className="accent-[#10b981]"
              />
              Rookies only
            </label>
            {/* Control is a SIBLING of its <label>, never nested. This is `Picker` (Radix), not a
                raw <select>: on iOS the native popup anchored to the top-left of the page no matter
                the font-size or label nesting. See components/ui/picker.tsx. */}
            <div className="ml-auto flex items-center gap-1.5 text-xs text-gray-400">
              <label htmlFor={scoringSelectId} className="text-gray-500">
                Reference scoring
              </label>
              <Picker
                id={scoringSelectId}
                value={effScoring}
                onValueChange={(v) => setScoring(v as Scoring)}
                ariaLabel="Reference scoring"
                className="h-auto rounded border border-[#262626] bg-[#0f0f0f] px-2 py-1 text-base sm:text-xs text-gray-200 focus:border-[#10b981]"
                options={(Object.keys(SCORING_LABEL) as Scoring[]).map((s) => {
                  // Listed and disabled, never removed — same reasoning as the board's format
                  // picker: a menu showing only the free option makes it look like the only
                  // scoring we publish, which is untrue and is the opposite of an upgrade prompt.
                  const lockedOption = !entitled && s !== FREE_SCORING
                  return {
                    value: s,
                    label: lockedOption
                      ? `${SCORING_LABEL[s]} · ${FORMAT_LOCK_SUFFIX}`
                      : SCORING_LABEL[s],
                    disabled: lockedOption,
                  }
                })}
              />
            </div>
          </div>

          {!entitled && (
            <p
              data-testid="reference-scoring-lock-note"
              className="mb-3 text-[11px] leading-relaxed text-gray-500"
            >
              {REFERENCE_SCORING_LOCK_NOTE}
            </p>
          )}

          <p className="mb-3 text-[11px] text-gray-600">
            {`The points column is a reference ${SCORING_LABEL[
              effScoring
            ].toLowerCase()} scoring used to order this table — for your league's own scoring and roster shape, use Rankings or the League Board.`}
          </p>

          <div className="mb-3">
            <Pagination
              page={page}
              pageSize={pageSize}
              total={rows.length}
              onPage={setPage}
              onPageSize={setPageSize}
            />
          </div>

          <div className="overflow-x-auto rounded-lg border border-[#262626]">
            {/* min-width bumped for the added full-season-rate column; the wrapper scrolls. */}
            <table className="w-full min-w-[980px] text-left text-xs">
              <thead className="bg-[#0f0f0f] text-gray-500">
                <tr>
                  <th className="px-3 py-2 font-medium">#</th>
                  <th className="px-3 py-2 font-medium">Player</th>
                  <th className="px-3 py-2 font-medium">Pos</th>
                  <th className="px-3 py-2 font-medium">Team</th>
                  <th className="px-3 py-2 text-right font-medium">Bye</th>
                  {/* The bare "G" told a reader nothing about why the points column sits where it
                      does. Same figure, named and defined: it is the availability factor the
                      points column is scaled by. */}
                  <th className="px-3 py-2 text-right font-medium">
                    <InfoTip label={PROJECTED_GAMES_LABEL}>{GLOSSARY.projectedGames}</InfoTip>
                  </th>
                  {statCols.map((c) => (
                    <th key={String(c.key)} className="px-3 py-2 text-right font-medium">
                      {c.label}
                    </th>
                  ))}
                  {/* "Proj" was silent about the single most misread property of this number: it
                      is an EXPECTED total with missed-game risk already priced in, so it reads low
                      against an "if he plays every week" projection from anywhere else. */}
                  <th className="px-3 py-2 text-right font-medium">
                    <InfoTip label={EXPECTED_POINTS_LABEL}>{GLOSSARY.expectedPoints}</InfoTip>
                  </th>
                  {/* The same total re-expressed over a full 17 games — kept immediately beside the
                      expected total, because the PAIR is the disclosure. See the rankings board. */}
                  <th className="px-3 py-2 text-right font-medium">
                    <InfoTip label={FULL_SEASON_RATE_LABEL}>{GLOSSARY.fullSeasonRate}</InfoTip>
                  </th>
                  {/* The interval is carried on the PPR total only, so it is labelled that way
                      rather than silently implying it tracks the selected reference scoring. */}
                  <th className="px-3 py-2 font-medium">80% range (PPR)</th>
                  {hasAdp && (
                    <th className="px-3 py-2 text-right font-medium">
                      <InfoTip label="ADP">
                        {GLOSSARY.adp}
                        {` Sample: ${data?.adp_format ?? "ppr"}, ${data?.adp_teams ?? 12}-team — this page is scoring-independent, so the reference is pinned rather than varying.`}
                      </InfoTip>
                    </th>
                  )}
                  <th className="px-3 py-2 font-medium">
                    <InfoTip label="Confidence">{GLOSSARY.confidence}</InfoTip>
                  </th>
                  <th className="px-3 py-2 font-medium">
                    <InfoTip label="Range basis">
                      Where this player&apos;s 80% range comes from.{" "}
                      {UNCERTAINTY_HELP.empirical} {UNCERTAINTY_HELP.calibrated_per_player}
                    </InfoTip>
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#1a1a1a]">
                {paged.map(({ player: p, rank }) => (
                  <tr key={p.id} className="hover:bg-[#0f0f0f]">
                    {/* the rank carried from the unsearched board — searching must not renumber */}
                    <td className="px-3 py-2 text-gray-600">{rank}</td>
                    <td className="px-3 py-2">
                      <Link
                        href={`/fantasy/player/${p.id}`}
                        className="flex items-center gap-1.5 font-medium text-gray-200 hover:text-[#10b981] hover:underline"
                      >
                        <span>{p.name}</span>
                        {p.rookie && <RookieBadge />}
                      </Link>
                      {p.rookie && p.draftPick != null && (
                        <span className="text-[10px] text-gray-600">Pick {p.draftPick}</span>
                      )}
                    </td>
                    <td className="px-3 py-2">
                      <PosBadge pos={p.pos} />
                    </td>
                    <td className="px-3 py-2 text-gray-400">{teamLabel(p)}</td>
                    <td className="px-3 py-2 text-right text-gray-500">{p.bye ?? "—"}</td>
                    {/* NF-C8 — the availability flag; see `AvailabilityFlag`. Unflagged, locked
                        and games-less rows all render exactly as they did before. */}
                    <td className="px-3 py-2 text-right text-gray-400">
                      <AvailabilityFlag
                        games={p.g}
                        locked={p.locked}
                        freshness={data?.freshness}
                        underDefinedHeader
                      />
                      {/* NF-C9 — see `WeeklyDesignation`. Same component, same feed vintage
                          and same disclaimer the Rankings board renders. */}
                      <WeeklyDesignation status={p.gameStatus} freshness={data?.freshness} />
                    </td>
                    {statCols.map((c) => (
                      <td key={String(c.key)} className="px-3 py-2 text-right text-gray-400">
                        {/* NF-INJ1-C — the server withheld this row's counting-stat line because
                            its per-game rate is one no NFL player has ever posted (NF-INJ1's
                            recorded envelope). ⚠️ BRANCHED ON THE ROW'S OWN MARKER, never on the
                            value being null: a null here is an honest "he has no such stat", and
                            collapsing the two is the E9.56c inversion. Ordered BEFORE the lock
                            check because the two are disjoint by construction — the marker only
                            ever reaches an ENTITLED payload, since `/projections-full` is the only
                            route that serves a stat line at all. */}
                        {isStatWithheld(p.statLineWithheld, String(c.key)) ? (
                          <WithheldStat />
                        ) : (
                          numOrLock(p[c.key] as number | null, p.locked, c.nd ?? 1)
                        )}
                      </td>
                    ))}
                    <td className="px-3 py-2 text-right font-semibold text-gray-100">
                      {numOrLock(p[effScoring], p.locked)}
                    </td>
                    {/* ⚠️ Scaled from the SELECTED reference scoring, so it tracks the picker rather
                        than silently quoting PPR while the column beside it shows standard. Null
                        (no/zero expected games) renders as an em-dash — never a blank, never ∞. */}
                    <td className="px-3 py-2 text-right text-gray-400">
                      {p.locked ? (
                        <LockChip title="Subscribe to unlock the full-season rate" />
                      ) : (
                        num(fullSeasonRate(p[effScoring], p.g))
                      )}
                    </td>
                    {/* E9.56 — the interval is model output too. A locked row has no p10/p90, so
                        render the chip rather than an empty bar that reads as "no uncertainty". */}
                    <td className="w-40 px-3 py-2">
                      {p.locked ? (
                        <LockChip title="Subscribe to unlock the projected range" />
                      ) : (
                        <>
                          <RangeCell p10={p.fpP10} p90={p.fpP90} classLevel={p.uncType === "calibrated"} />
                          <IntervalBar
                            p10={p.fpP10}
                            point={p.fpPpr}
                            p90={p.fpP90}
                            min={domain.min}
                            max={domain.max}
                            classLevel={p.uncType === "calibrated"}
                          />
                        </>
                      )}
                    </td>
                    {hasAdp && (
                      <td className="px-3 py-2 text-right text-gray-400">
                        {p.adp != null ? num(p.adp) : "—"}
                      </td>
                    )}
                    {/* 🚨 E9.56c — Confidence and Range basis are MODEL OUTPUT and are stripped from
                        a locked row, so both fell through to their own honest-absence renderings:
                        ConfidenceBadge's "—" and the ternary's "—". That silently converts a
                        WITHHELD value into "we have nothing for this player" — the exact inversion
                        the `numOrLock` note above this file's lock helpers exists to prevent, just
                        in the two cells that don't route through it. Every withheld point must
                        carry a chip (the story's rule), so branch on the row's own marker. */}
                    <td className="px-3 py-2">
                      {p.locked ? (
                        <LockChip title="Subscribe to unlock the model's confidence tier" />
                      ) : (
                        <ConfidenceBadge conf={p.conf} />
                      )}
                    </td>
                    <td
                      className="px-3 py-2 text-gray-500"
                      title={!p.locked && p.uncType ? UNCERTAINTY_HELP[p.uncType] : undefined}
                    >
                      {p.locked ? (
                        <LockChip title="Subscribe to unlock how this player's range was built" />
                      ) : p.uncType ? (
                        UNCERTAINTY_LABEL[p.uncType] ?? p.uncType
                      ) : (
                        "—"
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="mt-3">
            <Pagination
              page={page}
              pageSize={pageSize}
              total={rows.length}
              onPage={setPage}
              onPageSize={setPageSize}
            />
          </div>

          {/* E9.56b — say what was trimmed. `trimLockedTail` hides locked rows with no market ADP
              (~74% of the payload: names with a padlock and nothing else). Stating the count keeps
              the truncation honest AND makes it a reason to subscribe rather than a silent gap. */}
          {hiddenCount > 0 && (
            <p className="mt-3 text-center text-xs text-gray-500">
              {hiddenCount.toLocaleString()} more players — those undrafted in the market sample —
              are projected and included with a{" "}
              <a href={SUBSCRIBE_HREF} className="text-amber-400 hover:text-amber-300 hover:underline">
                subscription
              </a>
              .
            </p>
          )}

          <div className="mt-6">
            <UncertaintyNote>
              <p className="mt-2">
                <span className="font-semibold text-gray-300">Two kinds of range.</span>{" "}
                {UNCERTAINTY_HELP.empirical} {UNCERTAINTY_HELP.calibrated_per_player}
              </p>
              <p className="mt-2">
                <span className="font-semibold text-gray-300">Kickers and defences.</span>{" "}
                Both are now projected, but they are the least predictable positions in fantasy and
                the projection is deliberately a base one. A kicker&apos;s accuracy barely carries
                from one year to the next, and a defence&apos;s touchdowns, safeties and blocked
                kicks are indistinguishable from noise — so those are set to the league average
                rather than guessed per team. What does carry is the team around them: a
                kicker&apos;s scoring offence and leg strength, and a defence&apos;s sacks,
                takeaways and points allowed. Read them as streaming tiers — better situations
                versus worse ones — not as precise ranks, and lean on the range.
              </p>
              <p className="mt-2">The 80% range shown is on the reference PPR total.</p>
              <MarketLeanNote lean={data?.market_lean} note={data?.market_lean_note} />
            </UncertaintyNote>
          </div>

          {/* Below the complete table, for the reason given on the rankings board: the boundary
              only means something once the visitor has seen that nothing is withheld. */}
          <FreemiumBoundary entitled={entitled} />
        </>
      )}
    </div>
  )
}
