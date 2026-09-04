"use client"

// NCAAF-P3.3 — the team stats page.
//
// ⭐ NCAAF IS FREE (E9.45 — fantasy is the paid hook). No guard, no token, no entitlement branch
// anywhere in this tree; `/ncaaf/teams/{id}` reads no Bearer token at all.
//
// ══ WHAT THIS PAGE CLAIMS, AND WHAT IT REFUSES TO ═════════════════════════════════════════════
//
// It says how strong the model thinks a team is AND how sure it is, and it stops there.
// `best_alpha = 0` — VAL1 came back ALL_BUCKETS_NULL, ATS 0.496 against the close, indistinguishable
// from a placebo — so a strength rating is CONTEXT for reading a game, never a recommendation about
// one. There is no ranking, no "best team", no ordering of teams anywhere on this surface: a rank
// is the shape a reader most easily converts into a pick.
//
// ══ THE THREE EMPTY STATES ARE THREE DIFFERENT FACTS ══════════════════════════════════════════
//
//   * NO SUCH TEAM  — the API answers 404. An ordinary answer (a non-FBS id, a season not yet
//                     written), not a fault, which is why the query does not retry it.
//   * A FAILED READ — anything else. "We could not reach the model" is our problem and says so.
//   * A BLOCK WITH NOTHING IN IT — handled per block, with the server's own machine-readable
//                     reason, because on a September Saturday a CORRECT page has two of them.
//
// ⚠️ AND THE PARTIAL PAGE IS THE ORDINARY PAGE. Measured on the wire 2026-09-03: every 2026 team
// serves an available strength block and schedule, with efficiency and splits stating their own
// absence. A page that hid itself until all four blocks were present would be blank for the whole
// of September.

import Link from "next/link"
import { apiErrorStatus } from "@/lib/api"
import {
  CONFERENCE_MISMATCH_NOTE,
  NEW_TO_FBS_LABEL,
  NEW_TO_FBS_NOTE,
  TEAM_NOT_FOUND,
  TEAM_PAGE_STANDFIRST,
  TEAM_PAGE_TITLE_SUFFIX,
  TEAM_PROVENANCE_LABEL,
  TEAM_READ_FAILED,
} from "@/lib/ncaaf-copy"
import { formatRecord, isMarketBlindProjection, useNcaafTeam } from "@/lib/ncaaf-team"
import { NcaafTeamEfficiencyBlock, NcaafTeamSplitsBlock } from "./team-efficiency"
import { NcaafTeamScheduleBlock } from "./team-schedule"
import { NcaafTeamStrengthBlock } from "./team-strength"
import { NcaafTeamLogo } from "./team-logo"

function Notice({ testId, tone = "muted", children }: {
  testId: string
  tone?: "muted" | "warn"
  children: React.ReactNode
}) {
  return (
    <p
      data-testid={testId}
      className={
        "rounded-lg border px-3 py-2 text-xs leading-relaxed " +
        (tone === "warn"
          ? "border-amber-900/40 bg-amber-950/20 text-amber-200/80"
          : "border-[#1e1e1e] bg-[#0d0d0d] text-gray-400")
      }
    >
      {children}
    </p>
  )
}

function Skeleton({ testId }: { testId: string }) {
  return (
    <div data-testid={testId} className="space-y-3">
      <div className="h-8 w-48 animate-pulse rounded bg-[#161616]" />
      <div className="h-24 w-full animate-pulse rounded bg-[#141414]" />
    </div>
  )
}

export function NcaafTeamPageView({ teamId }: { teamId: string }) {
  const query = useNcaafTeam(teamId)

  // A team we publish nothing for answers 404, which is an ordinary answer here. Anything else is
  // a read that failed, and the two render differently because they are different facts (NF-C6b).
  const status = apiErrorStatus(query.error)
  const notFound = query.isError && status === 404
  const failed = query.isError && status !== 404

  const page = query.data
  const team = page?.team
  const record = page ? formatRecord(page.schedule) : null
  // ⛔ THE POSTURE IS BRANCHED ON, NOT ASSUMED. Every claim-bearing sentence on this page is
  // warranted by `market_blind && projection_only && best_alpha === 0` and by nothing else; on a
  // payload that stopped carrying them the page shows the publisher's own disclosure instead of
  // continuing to describe a model it was not written for.
  const postureHolds = isMarketBlindProjection(page?.framing)

  return (
    <main className="mx-auto max-w-4xl px-4 py-8 sm:px-6">
      {query.isLoading && <Skeleton testId="ncaaf-team-loading" />}
      {notFound && <Notice testId="ncaaf-team-not-found">{TEAM_NOT_FOUND}</Notice>}
      {failed && (
        <Notice testId="ncaaf-team-error" tone="warn">
          {TEAM_READ_FAILED}
        </Notice>
      )}

      {page && team && (
        <>
          <header data-testid="ncaaf-team-header" data-team-id={team.team_id} className="space-y-2">
            <div className="flex items-center gap-2.5">
              <NcaafTeamLogo teamId={team.team_id} teamName={team.team ?? "team"} />
              <h1 data-testid="ncaaf-team-name" className="text-xl font-semibold text-white sm:text-2xl">
                {team.team ?? `Team ${team.team_id}`}
              </h1>
            </div>

            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-gray-400">
              {/* ⭐ THE CONFERENCE IS THE SEASON'S, resolved point-in-time through the SCD-2 dim by
                  the server. Eleven FBS programs moved for 2026 — a "current" read would file a
                  mover under the wrong league on the page whose job is to say who they play. The
                  season is rendered BESIDE it so the label is unambiguous about which year it
                  describes. */}
              {team.conference && (
                <span
                  data-testid="ncaaf-team-conference"
                  data-conference-source={team.conference_source ?? ""}
                >
                  {team.conference}
                </span>
              )}
              <span data-testid="ncaaf-team-season">{team.season} {TEAM_PAGE_TITLE_SUFFIX}</span>
              {record && (
                <span data-testid="ncaaf-team-record" className="tabular-nums text-gray-300">
                  {record}
                </span>
              )}
              {team.is_new_to_fbs === true && (
                <span
                  data-testid="ncaaf-team-new-to-fbs"
                  className="rounded border border-[#2a2a2a] px-1.5 py-px text-[10px] uppercase tracking-wide text-gray-400"
                >
                  {NEW_TO_FBS_LABEL}
                </span>
              )}
            </div>

            <p className="max-w-2xl text-sm leading-relaxed text-gray-400">
              {TEAM_PAGE_STANDFIRST}
            </p>

            {/* The SERVED disclosure, rendered VERBATIM (the `lib/ncaaf-copy.ts` rule 3): a
                paraphrase here would be claim copy no screening had ever looked at. */}
            <p
              data-testid="ncaaf-team-disclosure"
              data-posture={postureHolds ? page.framing.framing : "changed"}
              className="rounded-lg border border-[#1e1e1e] bg-[#0d0d0d] px-3 py-2 text-[11px] leading-relaxed text-gray-500"
            >
              {page.framing.disclosure}
            </p>
          </header>

          {team.is_new_to_fbs === true && (
            <Notice testId="ncaaf-team-new-to-fbs-note">{NEW_TO_FBS_NOTE}</Notice>
          )}
          {/* ⚠️ A statement about OUR inputs, not about the team: the SCD-2 dim and the conference
              the posterior was POOLED under disagree, so the rating was shrunk toward a league this
              team does not play in. It is served as a flag precisely so a surface can say it. */}
          {team.conference_matches_model_input === false && (
            <Notice testId="ncaaf-team-conference-mismatch" tone="warn">
              {CONFERENCE_MISMATCH_NOTE}
            </Notice>
          )}

          <div className="mt-6 space-y-8">
            <NcaafTeamStrengthBlock strength={page.strength} />
            <NcaafTeamEfficiencyBlock efficiency={page.efficiency} />
            <NcaafTeamSplitsBlock splits={page.splits} />
            <NcaafTeamScheduleBlock schedule={page.schedule} />
          </div>

          <footer data-testid="ncaaf-team-provenance" className="mt-8 space-y-1 border-t border-[#1a1a1a] pt-4">
            <h2 className="text-[11px] font-medium uppercase tracking-wide text-gray-500">
              {TEAM_PROVENANCE_LABEL}
            </h2>
            <p className="text-[11px] text-gray-600">
              {page.strength.model_version ?? page.provenance.model_version ?? "—"}
              {page.strength.hyper_n_prior_seasons !== null &&
                ` · calibrated on ${page.strength.hyper_n_prior_seasons} prior season${
                  page.strength.hyper_n_prior_seasons === 1 ? "" : "s"
                }`}
              {" · built "}
              {page.generated_at.slice(0, 10)}
            </p>
            <Link
              data-testid="ncaaf-team-back-to-games"
              href="/ncaaf/games"
              className="inline-block text-[11px] text-gray-500 underline decoration-dotted underline-offset-2 transition-colors hover:text-gray-300"
            >
              College football projections
            </Link>
          </footer>
        </>
      )}
    </main>
  )
}
