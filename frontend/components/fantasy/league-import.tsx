"use client"

// NF-C0 — PLATFORM LEAGUE IMPORT: pull the user's real league in from Sleeper or Yahoo.
//
// 🎯 THE CONTRACT. An import produces the SAME `LeagueConfig` the manual NF-C0b editor produces and
// saves it through the SAME `/fantasy/leagues` endpoints. Downstream — board, rankings, VOR, draft
// optimizer — cannot tell an imported league from a typed-in one, and a config is portable between
// the two paths. There is deliberately no second settings schema.
//
// 🚨 NO PASSWORDS, EVER. Sleeper is a public read-only API and needs no credential. Yahoo goes
// through Yahoo's OWN consent screen (OAuth) and we hold only an encrypted, revocable, read-scoped
// grant. ESPN is absent on purpose: its only route to a private league is replaying full-account
// session cookies, so ESPN users take the manual editor — which already works.
//
// ⭐ PREVIEW BEFORE SAVE, AND SAY WHAT WE COULD NOT DO. A platform scores things our projection does
// not produce. The preview shows the honest coverage verdict for EVERY term BEFORE the league is
// saved, so a user agrees to the translation rather than discovering later that a rule they care
// about silently scored nothing. That verdict is computed by `resolveScoring` against the
// projection columns that actually exist — this surface cannot promote a term by asserting it.

import { useEffect, useMemo, useState } from "react"
import Link from "next/link"
import { useSearchParams } from "next/navigation"
import posthog from "posthog-js"
import {
  AlertTriangle,
  ArrowRight,
  Check,
  Download,
  Link2,
  Loader2,
  Lock,
  Unlink,
} from "lucide-react"
import { useAuth } from "@/lib/auth-context"
import { useFantasyProjections, useSaveLeague, useSavedLeagues } from "@/lib/fantasy-queries"
import {
  espnPreview,
  espnReadUrl,
  listImportPlatforms,
  recordCapturedTermTelemetry,
  sleeperLeagues,
  sleeperPreview,
  yahooAuthorizeUrl,
  yahooDisconnect,
  yahooLeagues,
  yahooPreview,
  type ImportPlatform,
  type ImportPreview,
  type PlatformLeagueSummary,
} from "@/lib/fantasy-import"
import type { LeagueSaveInput } from "@/lib/fantasy"
import { resolveScoring, type TermCoverage } from "@/lib/league-config"
import { availableFields } from "@/lib/league-scoring"
import { canSaveAnotherLeague } from "@/lib/entitlements"
import {
  LEAGUE_QUOTA_REACHED_DETAIL,
  LEAGUE_QUOTA_REACHED_TITLE,
} from "@/lib/fantasy-claim-copy"
import {
  EmptyBlock,
  LeagueQuotaNotice,
  LoadingBlock,
  SurfaceHeader,
  num,
} from "@/components/fantasy/shared"

const SEASON = process.env.NEXT_PUBLIC_NFL_FANTASY_SEASON ?? "2026"

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

/** Turn a thrown API error into something a person can act on.
 *
 *  ⚠️ THE SERVER'S MESSAGE WINS. `apiFetch` now surfaces the API's own `detail`, which is written to
 *  be read by a user ("Sleeper has no user called 'X' — check the spelling, or paste your league ID
 *  instead"). Substituting a generic string keyed off the status code would throw away the only
 *  message that actually says what to DO — so the fallbacks below fire only for a bare
 *  `API error <status>`, i.e. when the server sent no detail at all. */
function errorText(e: unknown): string {
  const message = e instanceof Error ? e.message : String(e)
  if (!/^API error \d+$/.test(message)) return message || "Something went wrong."
  if (/40[13]/.test(message)) return "You do not have access to league import yet."
  if (/429/.test(message)) return "The platform is rate-limiting us. Try again in a moment."
  if (/503/.test(message)) return "That platform is not connected yet."
  return "Something went wrong. Please try again."
}

export function LeagueImport() {
  const { accessToken, groups } = useAuth()
  const search = useSearchParams()
  const saveLeague = useSaveLeague()
  const { data: savedLeagues } = useSavedLeagues()
  const { data: projections } = useFantasyProjections()

  // ── G100-C1 (live fix): THE QUOTA, ENFORCED ON THIS PATH TOO ──────────────────────────────────
  //
  // There are two ways to create a league and the first cut gated only the manual editor, so a free
  // account at its quota was refused by the form and waved through by the importer — all the way to
  // a 409 it met after picking a platform, entering a username, waiting on a preview and pressing
  // Save. Refusing that late is worse than refusing at all: the work is already done.
  //
  // ⚠️ THE RULE IS "A DIFFERENT LEAGUE", NOT "ANY IMPORT". Re-importing a league you already saved
  // is an UPDATE — it creates nothing, the server's cap does not apply to it (`PUT`), and it is how
  // you refresh a roster mid-season. Blocking it would break the re-sync every returning user needs,
  // to enforce a limit that was never exceeded. So the block is keyed on whether THIS preview would
  // create a SECOND league.
  const atQuota = !canSaveAnotherLeague((savedLeagues ?? []).length, groups)
  /** The saved league this platform league already maps to, if any — the update case. */
  const savedMatchFor = (platform: string | null, sourceLeagueId: string | null) =>
    (savedLeagues ?? []).find(
      (l) => l.source_platform === platform && l.source_league_id === sourceLeagueId,
    ) ?? null

  const [platforms, setPlatforms] = useState<ImportPlatform[] | null>(null)
  const [platformId, setPlatformId] = useState<string>("sleeper")
  const [username, setUsername] = useState("")
  const [leagues, setLeagues] = useState<PlatformLeagueSummary[] | null>(null)
  const [preview, setPreview] = useState<ImportPreview | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState<string | null>(null)
  // NF-C0c — which team roster rows are expanded to show their players. Collapsed by default: a
  // 12-team league can carry 300+ roster spots, so showing every name up front would bury the
  // settings review this page exists for.
  const [expandedTeams, setExpandedTeams] = useState<Set<string>>(new Set())
  // NF-C6 — which previewed team is the user's OWN, so "My Teams" knows what to score. Pre-filled
  // from `is_owner` when the platform told us (Yahoo's OAuth identity); Sleeper and ESPN cannot
  // auto-detect this (see the `source_team_key` field docstring), so the user picks it here. `null`
  // is a legitimate, saveable choice — a league without a linked team just shows "not linked yet".
  const [selectedTeamKey, setSelectedTeamKey] = useState<string | null>(null)

  // ESPN: the league id the user reads off their own URL, the link we build for them to open, and
  // the response body they bring back. `espnPaste` holds a credential-free settings blob — it is
  // sent once and never persisted here.
  const [espnLeagueId, setEspnLeagueId] = useState("")
  const [espnLink, setEspnLink] = useState<string | null>(null)
  const [espnPaste, setEspnPaste] = useState("")
  const [espnCopied, setEspnCopied] = useState(false)

  // The Yahoo callback returns the browser here with a status flag rather than a JSON body — the
  // user is mid-flow in a browser, so the outcome has to be visible on the page they land on.
  const yahooFlag = search.get("yahoo")

  /** Would saving THIS preview create a second league the caller has no quota for? Recomputed from
   *  the preview rather than latched at pick time, so the ESPN paste path — which produces a preview
   *  without ever going through the league list — is covered by the same flag. */
  const previewBlockedByQuota =
    !!preview && atQuota && !savedMatchFor(preview.platform, preview.source_league_id)

  const refreshPlatforms = useMemo(
    () => async () => {
      try {
        setPlatforms(await listImportPlatforms(accessToken))
      } catch (e) {
        setError(errorText(e))
      }
    },
    [accessToken],
  )

  useEffect(() => {
    void refreshPlatforms()
  }, [refreshPlatforms])

  useEffect(() => {
    if (yahooFlag === "connected") {
      setPlatformId("yahoo")
      void refreshPlatforms()
    }
  }, [yahooFlag, refreshPlatforms])

  const platform = platforms?.find((p) => p.id === platformId) ?? null

  // ── the honest coverage report for the PREVIEWED config ────────────────────────────────────
  // Computed exactly as the manual editor computes it, against the projection columns actually
  // present — so the two surfaces cannot disagree about what a given league setting will do.
  const coverage = useMemo(() => {
    if (!preview) return null
    return resolveScoring(preview.config.scoring, {
      availableFields: projections?.players ? availableFields(projections.players) : undefined,
      capturedRules: Object.keys(preview.config.captured_rules ?? {}),
    }).report
  }, [preview, projections])

  const byVerdict = (v: string): TermCoverage[] =>
    (coverage?.terms ?? []).filter((t) => t.verdict === v)

  async function run<T>(key: string, fn: () => Promise<T>): Promise<T | null> {
    setBusy(key)
    setError(null)
    try {
      return await fn()
    } catch (e) {
      setError(errorText(e))
      return null
    } finally {
      setBusy(null)
    }
  }

  async function findSleeperLeagues() {
    setPreview(null)
    const res = await run("sleeper-leagues", () =>
      sleeperLeagues(accessToken, username.trim(), SEASON),
    )
    if (!res) return
    if (res.kind === "league") {
      // They pasted a league ID — there is nothing to pick from, so go straight to the preview
      // rather than making them choose their league out of a list of one.
      setLeagues([res.league])
      await loadPreview(res.league.league_id)
      return
    }
    // `?? []` is the client half of the additive-response rule: if a response ever arrives WITHOUT
    // the key we read, fall through to the visible "no leagues found" empty state rather than
    // leaving `leagues` undefined, which renders nothing at all and looks like a dead button.
    setLeagues(res.leagues ?? [])
  }

  async function buildEspnLink() {
    setPreview(null)
    setEspnCopied(false)
    const res = await run("espn-link", () =>
      espnReadUrl(accessToken, espnLeagueId.trim(), SEASON),
    )
    if (res?.url) setEspnLink(res.url)
  }

  async function submitEspnPaste() {
    const res = await run("espn-preview", () =>
      espnPreview(accessToken, espnPaste, SEASON),
    )
    if (res) {
      applyPreview(res)
      // Drop the pasted blob as soon as it has been parsed. It holds no credential by construction,
      // but there is no reason to keep a user's league dump sitting in component state either.
      setEspnPaste("")
    }
  }

  async function connectYahoo() {
    const res = await run("yahoo-connect", () => yahooAuthorizeUrl(accessToken))
    if (res?.authorize_url) window.location.href = res.authorize_url
  }

  async function loadYahooLeagues() {
    setPreview(null)
    const res = await run("yahoo-leagues", () => yahooLeagues(accessToken))
    if (res) setLeagues(res.leagues)
  }

  /** Adopt a freshly-loaded preview, pre-selecting "my team" whenever the platform told us
   *  (Yahoo's `is_owner`, from real OAuth identity). Sleeper/ESPN leave it unselected — see the
   *  `selectedTeamKey` state doc — so the reviewer picks their own team from the list below. */
  function applyPreview(res: ImportPreview) {
    setPreview(res)
    setSaved(null)
    setSelectedTeamKey(res.teams.find((t) => t.is_owner)?.team_key ?? null)
  }

  async function loadPreview(leagueId: string) {
    // G100-D0's `league_import_started`. Fired when a specific league is chosen — the first
    // irreversible-feeling step and the one whose drop-off is worth measuring — rather than on page
    // view, which would count every visitor as having started an import. Its pair is
    // `league_import_completed` in `saveImported`, so the gap between them IS the import funnel.
    // ⛔ Do not rename: G100-D0's dashboard consumes these names.
    posthog.capture("league_import_started", { league_platform: platformId })
    const res = await run("preview", () =>
      platformId === "yahoo"
        ? yahooPreview(accessToken, leagueId)
        : sleeperPreview(accessToken, leagueId),
    )
    if (res) applyPreview(res)
  }

  async function saveImported() {
    if (!preview) return
    // Re-importing a league you already saved UPDATES it rather than creating a duplicate. Two
    // copies of the same league is a silent trap: the user edits one and the board reads the other.
    const already = savedMatchFor(preview.platform, preview.source_league_id)
    // Belt and braces with the disabled button: a disabled control is presentation, and this is the
    // one call that would meet the server's 409. Refusing here keeps the reason on screen next to
    // the control instead of surfacing as a raw error string.
    if (atQuota && !already) return
    // NF-C6 — the team the reviewer picked below, if any. `null` is honest and saveable: the league
    // settings are still useful (rankings/board/draft) even before a roster is linked to it.
    const myTeam = preview.teams.find((t) => t.team_key === selectedTeamKey) ?? null
    const payload: LeagueSaveInput = {
      ...preview.config,
      source_platform: preview.platform,
      source_league_id: preview.source_league_id,
      imported_at: new Date().toISOString(),
      source_team_key: myTeam?.team_key ?? null,
      source_team_name: myTeam?.name ?? null,
      imported_roster: myTeam?.players ?? null,
      roster_synced_at: myTeam ? new Date().toISOString() : null,
    }
    const res = await run("save", () =>
      saveLeague.mutateAsync({ leagueId: already?.league_id ?? null, config: payload }),
    )
    if (res) {
      setSaved(already ? "updated" : "saved")

      // ── G100-C1: the SECOND clause of the activation definition ──────────────────────────────
      //
      // `account_created AND league_config_completed AND custom_board_viewed`. The manual editor
      // fires the SAME event with `method: "manual"` — activation is about HAVING a configured
      // league, not about which door it came through, and a funnel that counted only the imported
      // route would read the manual floor's users as never activating at all.
      //
      // `league_import_completed` is emitted BESIDE it (not instead of): it is G100-D0's own
      // platform-specific event, and the two answer different questions — "did import work for
      // Sleeper?" versus "does this account have a league?". ⛔ Neither name may be changed.
      //
      // ⭐ ONLY ON A CREATE. Re-importing an existing league is an UPDATE, and counting it as a
      // fresh activation would let one user inflate the denominator paid conversion is measured
      // against simply by re-syncing their roster.
      posthog.capture("league_import_completed", {
        league_platform: preview.platform,
        league_format: preview.config.ppr ?? null,
        league_size: preview.config.n_teams ?? null,
        updated: !!already,
      })
      if (!already) {
        posthog.capture("league_config_completed", {
          method: "import",
          league_platform: preview.platform,
          league_format: preview.config.ppr ?? null,
          league_size: preview.config.n_teams ?? null,
        })
      }

      // NF-C0d — coverage-gap telemetry: which settings this league scores that we could not
      // apply (the rule + its point value only, never anything about the user or their roster —
      // see recordCapturedTermTelemetry's docstring). Fire-and-forget: the import already
      // succeeded, so a telemetry failure here must stay invisible to the user.
      const capturedTerms = byVerdict("captured").map((t) => ({
        key: t.key,
        weight: t.weight,
        verdict: t.verdict,
      }))
      recordCapturedTermTelemetry(accessToken, preview.platform, preview.season, capturedTerms).catch(
        () => {},
      )
    }
  }

  if (!platforms) return <LoadingBlock label="Loading import options…" />

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      <SurfaceHeader
        title="Import your league"
        blurb="Pull your real league's scoring and roster settings straight from your platform. Everything the tools do — rankings, the board, the draft optimizer — then runs on YOUR format."
      />

      {yahooFlag === "connected" && (
        <Banner tone="ok">Yahoo connected. Pick the league you want to import.</Banner>
      )}
      {yahooFlag === "denied" && (
        <Banner tone="warn">
          You cancelled the Yahoo sign-in, so nothing was connected. You can try again, or enter your
          league by hand under My League Settings.
        </Banner>
      )}
      {yahooFlag === "failed" && (
        <Banner tone="warn">
          The Yahoo sign-in did not complete. Nothing was saved — try connecting again.
        </Banner>
      )}
      {error && <Banner tone="warn">{error}</Banner>}

      {/* ── platform picker ──────────────────────────────────────────────────────────────── */}
      <div className="mt-6 grid gap-3 sm:grid-cols-2">
        {platforms.map((p) => (
          <button
            key={p.id}
            onClick={() => {
              setPlatformId(p.id)
              setLeagues(null)
              setPreview(null)
              setError(null)
            }}
            className={`rounded-lg border px-4 py-3 text-left transition ${
              platformId === p.id
                ? "border-emerald-500/50 bg-emerald-500/5"
                : "border-white/10 bg-white/[0.02] hover:border-white/20"
            }`}
          >
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-gray-100">{p.label}</span>
              {p.auth === "oauth" && p.connected && (
                <span className="flex items-center gap-1 text-[10px] text-emerald-400">
                  <Check className="h-3 w-3" /> connected
                </span>
              )}
              {p.auth === "oauth" && !p.configured && (
                <span className="rounded border border-amber-500/30 bg-amber-500/10 px-1.5 py-0.5 text-[10px] text-amber-400">
                  Coming soon
                </span>
              )}
            </div>
            {/* An OAuth platform we cannot reach YET must not describe itself as if it works —
                the backend's `help` is the connected-state copy, so swap it while pending. */}
            <p className="mt-1 text-xs text-gray-400">
              {p.auth === "oauth" && !p.configured
                ? "Coming soon — we've applied to Yahoo for access and are waiting on their approval."
                : p.help}
            </p>
          </button>
        ))}
      </div>

      {/* The remaining platforms. Named rather than omitted: a user who doesn't see their platform
          assumes the feature is broken, so point at the floor that already works. */}
      <p className="mt-3 text-xs text-gray-500">
        On <span className="text-gray-400">CBS, MyFantasyLeague or Fantrax?</span> Those have no
        import yet — enter your league once under{" "}
        <a href="/fantasy/league-settings" className="text-emerald-400 hover:underline">
          My League Settings
        </a>{" "}
        and every tool works exactly the same.
      </p>

      {/* ── step 1: find the leagues ─────────────────────────────────────────────────────── */}
      <section className="mt-8">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-gray-400">
          1 · Find your league
        </h2>

        {platformId === "sleeper" && (
          <div className="mt-3">
            {/* ⭐ Lead with the LEAGUE ID, not the username. The ID is the identifier a user can
                actually obtain (it is sitting in the league's URL); a username has to be recalled
                and is the thing people get wrong. The username is offered second, as the fallback
                for "I don't know my league ID." */}
            <div className="flex flex-wrap items-center gap-2">
              {/* text-base on phones (iOS auto-zooms on focus below 16px), text-sm from sm: up. */}
              <input
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && username.trim() && void findSleeperLeagues()}
                placeholder="Paste your Sleeper league ID"
                className="w-72 rounded border border-white/10 bg-white/[0.03] px-3 py-2 text-base sm:text-sm text-gray-100 placeholder:text-gray-600 focus:border-emerald-500/50 focus:outline-none"
              />
              <button
                onClick={() => void findSleeperLeagues()}
                disabled={!username.trim() || busy === "sleeper-leagues"}
                className="flex items-center gap-1.5 rounded bg-emerald-600 px-3 py-2 text-sm font-medium text-white disabled:opacity-40"
              >
                {busy === "sleeper-leagues" ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <ArrowRight className="h-3.5 w-3.5" />
                )}
                Import
              </button>
            </div>

            <div className="mt-3 rounded-lg border border-white/10 bg-white/[0.02] p-3">
              <div className="text-[11px] font-semibold uppercase tracking-wide text-gray-400">
                Where to find your league ID
              </div>
              <ol className="mt-2 space-y-1 text-xs text-gray-400">
                <li>
                  <span className="text-gray-500">1.</span> Open your league at{" "}
                  <a
                    href="https://sleeper.app"
                    target="_blank"
                    rel="noreferrer"
                    className="text-emerald-400 hover:underline"
                  >
                    sleeper.app
                  </a>{" "}
                  in a browser (the mobile app does not show the ID).
                </li>
                <li>
                  <span className="text-gray-500">2.</span> Look at the address bar — the league ID
                  is the long number after <span className="text-gray-500">/leagues/</span>:
                </li>
              </ol>
              <div className="mt-2 overflow-x-auto rounded bg-black/40 px-2.5 py-1.5 font-mono text-[11px] text-gray-500">
                sleeper.app/leagues/
                <span className="rounded bg-emerald-500/15 px-1 text-emerald-300">
                  1234567890123456789
                </span>
                /team
              </div>
              <p className="mt-2 text-xs text-gray-500">
                Don&apos;t have it handy? Enter your{" "}
                <span className="text-gray-400">Sleeper username</span> in the box above instead and
                we&apos;ll list your leagues to pick from.
              </p>
              <p className="mt-1 text-[11px] text-gray-600">
                Sleeper league data is public, so this needs no sign-in and no password.
              </p>
            </div>
          </div>
        )}

        {platformId === "espn" && (
          <div className="mt-3">
            {/* Step A — the league ID, exactly as Sleeper asks for it. */}
            <div className="flex flex-wrap items-center gap-2">
              {/* text-base on phones (iOS auto-zooms on focus below 16px), text-sm from sm: up. */}
              <input
                value={espnLeagueId}
                onChange={(e) => setEspnLeagueId(e.target.value)}
                onKeyDown={(e) =>
                  e.key === "Enter" && espnLeagueId.trim() && void buildEspnLink()
                }
                placeholder="Paste your ESPN league ID"
                className="w-72 rounded border border-white/10 bg-white/[0.03] px-3 py-2 text-base sm:text-sm text-gray-100 placeholder:text-gray-600 focus:border-emerald-500/50 focus:outline-none"
              />
              <button
                onClick={() => void buildEspnLink()}
                disabled={!espnLeagueId.trim() || busy === "espn-link"}
                className="flex items-center gap-1.5 rounded bg-emerald-600 px-3 py-2 text-sm font-medium text-white disabled:opacity-40"
              >
                {busy === "espn-link" ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Link2 className="h-3.5 w-3.5" />
                )}
                Get my link
              </button>
            </div>

            <div className="mt-3 rounded-lg border border-white/10 bg-white/[0.02] p-3">
              <div className="text-[11px] font-semibold uppercase tracking-wide text-gray-400">
                Where to find your league ID
              </div>
              <p className="mt-2 text-xs text-gray-400">
                Open your league on{" "}
                <a
                  href="https://fantasy.espn.com/football/"
                  target="_blank"
                  rel="noreferrer"
                  className="text-emerald-400 hover:underline"
                >
                  fantasy.espn.com
                </a>{" "}
                and look at the address bar — the ID is the number after{" "}
                <span className="text-gray-500">leagueId=</span>:
              </p>
              <div className="mt-2 overflow-x-auto rounded bg-black/40 px-2.5 py-1.5 font-mono text-[11px] text-gray-500">
                fantasy.espn.com/football/league?leagueId=
                <span className="rounded bg-emerald-500/15 px-1 text-emerald-300">998005</span>
              </div>
            </div>

            {/* Step B — the link, and the paste box. Only shown once we have a link, so the flow
                reads as two steps instead of one intimidating wall. */}
            {espnLink && (
              <div className="mt-4 rounded-lg border border-emerald-500/20 bg-emerald-500/[0.04] p-3">
                <div className="text-[11px] font-semibold uppercase tracking-wide text-emerald-400">
                  Open this link, then copy what you see
                </div>
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  <a
                    href={espnLink}
                    target="_blank"
                    rel="noreferrer"
                    className="flex items-center gap-1.5 rounded bg-emerald-600 px-3 py-2 text-sm font-medium text-white"
                  >
                    <ArrowRight className="h-3.5 w-3.5" />
                    Open my league settings
                  </a>
                  <button
                    onClick={() => {
                      void navigator.clipboard?.writeText(espnLink)
                      setEspnCopied(true)
                    }}
                    className="rounded border border-white/10 px-3 py-2 text-sm text-gray-300 hover:bg-white/5"
                  >
                    {espnCopied ? "Copied" : "Copy link"}
                  </button>
                </div>
                <ol className="mt-3 space-y-1 text-xs text-gray-400">
                  <li>
                    <span className="text-gray-500">1.</span> The link opens a page of text starting
                    with <span className="font-mono text-gray-500">{"{"}</span>. You must be signed
                    in to ESPN — it&apos;s your league, so your browser handles that.
                  </li>
                  <li>
                    <span className="text-gray-500">2.</span> Select all of it and copy
                    (<span className="text-gray-500">Ctrl/⌘ + A</span>, then{" "}
                    <span className="text-gray-500">Ctrl/⌘ + C</span>).
                  </li>
                  <li>
                    <span className="text-gray-500">3.</span> Paste it below.
                  </li>
                </ol>
                <textarea
                  value={espnPaste}
                  onChange={(e) => setEspnPaste(e.target.value)}
                  rows={5}
                  placeholder='Paste the text here — it starts with {"draftDetail":…'
                  className="mt-3 w-full rounded border border-white/10 bg-black/30 px-3 py-2 font-mono text-base sm:text-xs text-gray-300 placeholder:text-gray-600 focus:border-emerald-500/50 focus:outline-none"
                />
                <button
                  onClick={() => void submitEspnPaste()}
                  disabled={!espnPaste.trim() || busy === "espn-preview"}
                  className="mt-2 flex items-center gap-1.5 rounded bg-emerald-600 px-3 py-2 text-sm font-medium text-white disabled:opacity-40"
                >
                  {busy === "espn-preview" ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Download className="h-3.5 w-3.5" />
                  )}
                  Read my league
                </button>
                {/* Sets the expectation BEFORE the paste. Most people import pre-draft, so an
                    empty roster is the common outcome and must not read as a broken import — the
                    preview says so again, per league, once we can see the actual draft state. */}
                <p className="mt-2 text-[11px] leading-relaxed text-gray-500">
                  This brings over your scoring, roster shape, teams and rosters. If you
                  haven&apos;t drafted yet there are no rosters to bring — that&apos;s expected, and
                  everything the draft tools need is in your settings. Import again afterwards to
                  pull the rosters.
                </p>
                {/* ⭐ The reason this flow is a copy-paste at all. Users will wonder why ESPN is
                    harder than Sleeper; saying it plainly turns friction into a reason to trust us,
                    and pre-empts "why don't you just ask for my ESPN login?" */}
                <p className="mt-3 border-t border-white/5 pt-2 text-[11px] leading-relaxed text-gray-500">
                  <span className="text-gray-400">Why the copy-paste?</span> ESPN publishes no way
                  for another app to read a private league. The only automated route would be
                  handling your ESPN sign-in — which isn&apos;t read-only, isn&apos;t limited to
                  fantasy, and you couldn&apos;t revoke it for us alone — so we don&apos;t ask for
                  it. This way your browser makes the request and we only ever see the settings.
                </p>
              </div>
            )}
          </div>
        )}

        {platformId === "yahoo" && (
          <div className="mt-3">
            {!platform?.configured ? (
              // ⚠️ Attribute the timeframe to YAHOO, and don't promise a date we don't control:
              // "one to two weeks" is Yahoo's own stated review window, not our estimate. Pair it
              // with the floor so the user has something to do NOW rather than a date to wait for.
              <EmptyBlock
                title="Yahoo import is coming soon"
                detail="Yahoo requires an approved developer application before any league can be read, and we've applied. Yahoo says reviews take one to two weeks, so the timing is theirs — we'll switch this on the day it clears. In the meantime you can enter your Yahoo league by hand under My League Settings: it takes a few minutes and every tool then works exactly the same."
              />
            ) : platform.connected ? (
              <div className="flex flex-wrap items-center gap-2">
                <button
                  onClick={() => void loadYahooLeagues()}
                  disabled={busy === "yahoo-leagues"}
                  className="flex items-center gap-1.5 rounded bg-emerald-600 px-3 py-2 text-sm font-medium text-white disabled:opacity-40"
                >
                  {busy === "yahoo-leagues" ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <ArrowRight className="h-3.5 w-3.5" />
                  )}
                  Load my Yahoo leagues
                </button>
                <button
                  onClick={async () => {
                    await run("yahoo-disconnect", () => yahooDisconnect(accessToken))
                    setLeagues(null)
                    setPreview(null)
                    await refreshPlatforms()
                  }}
                  className="flex items-center gap-1.5 rounded border border-white/10 px-3 py-2 text-sm text-gray-300 hover:border-white/20"
                >
                  <Unlink className="h-3.5 w-3.5" /> Disconnect
                </button>
                {/* Says precisely what it does. We can delete OUR copy of the grant; only Yahoo can
                    revoke it, so we link there rather than implying we did it. */}
                <span className="text-xs text-gray-500">
                  Disconnecting deletes our copy of your Yahoo permission. To revoke it at Yahoo, use{" "}
                  <a
                    href="https://login.yahoo.com/account/security"
                    target="_blank"
                    rel="noreferrer"
                    className="text-emerald-400 hover:underline"
                  >
                    your Yahoo account settings
                  </a>
                  .
                </span>
              </div>
            ) : (
              <div className="flex flex-wrap items-center gap-2">
                <button
                  onClick={() => void connectYahoo()}
                  disabled={busy === "yahoo-connect"}
                  className="flex items-center gap-1.5 rounded bg-[#5f01d1] px-3 py-2 text-sm font-medium text-white disabled:opacity-40"
                >
                  {busy === "yahoo-connect" ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Link2 className="h-3.5 w-3.5" />
                  )}
                  Sign in with Yahoo
                </button>
                <span className="text-xs text-gray-500">
                  You sign in on Yahoo&apos;s own page and grant read-only access. We never see your
                  Yahoo password, and you can revoke the permission at any time.
                </span>
              </div>
            )}
          </div>
        )}

        {leagues && leagues.length === 0 && (
          <div className="mt-4">
            <EmptyBlock
              title={`No ${SEASON} leagues found`}
              detail="We could not see any league for that account this season. Check the season has started on your platform, or enter the league by hand under My League Settings."
            />
          </div>
        )}

        {leagues && leagues.length > 0 && (
          <>
            {/* ⭐ THE BOUNDARY IS DRAWN BEFORE THE WORK, not after it. Once the account is at its
                quota, every league here except the one already saved is unimportable — saying so
                above the list is what stops someone picking one, waiting for a preview and only
                then learning it cannot be saved. */}
            {atQuota && (
              <div className="mt-4">
                <LeagueQuotaNotice
                  title={LEAGUE_QUOTA_REACHED_TITLE}
                  detail={`${LEAGUE_QUOTA_REACHED_DETAIL} You can still re-import the league you already have to refresh its roster.`}
                  action={
                    <Link
                      href="/fantasy/league-settings"
                      className="text-gray-300 underline hover:text-[#10b981]"
                    >
                      Manage the league you have
                    </Link>
                  }
                />
              </div>
            )}
            <div className="mt-4 divide-y divide-white/5 rounded-lg border border-white/10">
              {leagues.map((l) => {
                const saved = savedMatchFor(platformId, l.league_id)
                // An import that would CREATE a second league is locked; re-importing the saved one
                // stays open, because that is an update and costs no quota.
                const locked = atQuota && !saved
                return (
                  <button
                    key={l.league_id}
                    onClick={() => {
                      if (locked) return
                      void loadPreview(l.league_id)
                    }}
                    disabled={locked}
                    data-testid={locked ? "import-league-locked" : "import-league-option"}
                    className="flex w-full items-center justify-between px-4 py-3 text-left hover:bg-white/[0.03] disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:bg-transparent"
                  >
                    <div>
                      <div className="text-sm text-gray-100">{l.name}</div>
                      <div className="text-xs text-gray-500">
                        {l.total_rosters || "?"}-team · {l.season}
                        {l.status ? ` · ${l.status.replace(/_/g, " ")}` : ""}
                        {saved ? " · already saved" : ""}
                      </div>
                    </div>
                    {locked ? (
                      <span className="flex items-center gap-1.5 text-xs text-gray-500">
                        <Lock className="h-3.5 w-3.5" /> Members only
                      </span>
                    ) : busy === "preview" ? (
                      <Loader2 className="h-4 w-4 animate-spin text-gray-500" />
                    ) : (
                      <ArrowRight className="h-4 w-4 text-gray-500" />
                    )}
                  </button>
                )
              })}
            </div>
          </>
        )}
      </section>

      {/* ── step 2: review, then save ────────────────────────────────────────────────────── */}
      {preview && (
        <section className="mt-10">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-gray-400">
            2 · Review what we read
          </h2>

          <div className="mt-3 rounded-lg border border-white/10 bg-white/[0.02] p-4">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <div>
                <div className="text-base font-medium text-gray-100">{preview.config.name}</div>
                <div className="mt-0.5 text-xs text-gray-500">
                  {preview.config.n_teams}-team · {preview.config.ppr.replace(/_/g, " ")}
                  {preview.config.superflex ? " · superflex" : ""} ·{" "}
                  {preview.platform === "yahoo" ? "Yahoo" : "Sleeper"}
                  {preview.season ? ` ${preview.season}` : ""}
                </div>
              </div>
              <button
                onClick={() => void saveImported()}
                disabled={busy === "save" || previewBlockedByQuota}
                className="flex items-center gap-1.5 rounded bg-emerald-600 px-3 py-2 text-sm font-medium text-white disabled:opacity-40"
              >
                {busy === "save" ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : previewBlockedByQuota ? (
                  <Lock className="h-3.5 w-3.5" />
                ) : (
                  <Download className="h-3.5 w-3.5" />
                )}
                Save this league
              </button>
            </div>

            {/* ⭐ THE OUTCOME BELONGS AT THE CONTROL. Errors render in a banner at the top of the
                page, which on this surface sits several hundred pixels above the Save button behind
                a full settings review — so a refused save looked like nothing happened at all, and
                the reason was only findable by scrolling back up. The banner stays (it is also
                where connect/preview failures land); this repeats the outcome where the click was.
                Same failure shape E8.6 fixed for the manual editor: a save that reports nothing is
                indistinguishable from a save that silently did not happen. */}
            {error && !busy && (
              <p
                className="mt-3 flex items-start gap-1.5 text-xs text-amber-400"
                data-testid="import-save-error"
                role="status"
              >
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                <span>{error}</span>
              </p>
            )}

            {previewBlockedByQuota && (
              <div className="mt-3">
                <LeagueQuotaNotice
                  title={LEAGUE_QUOTA_REACHED_TITLE}
                  detail={`${LEAGUE_QUOTA_REACHED_DETAIL} This one would be your second, so it can't be saved on a free account.`}
                  testId="import-quota-notice"
                  action={
                    <Link
                      href="/fantasy/my-league"
                      className="text-gray-300 underline hover:text-[#10b981]"
                    >
                      See the league you have
                    </Link>
                  }
                />
              </div>
            )}

            {saved && (
              <p className="mt-3 text-xs text-emerald-400">
                League {saved}. It now appears everywhere you pick a format — rankings, the board and
                the draft optimizer.
                {selectedTeamKey
                  ? " Your team is linked, so it will show up on My Teams too."
                  : " No team linked yet — pick yours above and save again to see it on My Teams."}
              </p>
            )}

            {/* starting lineup */}
            <div className="mt-4">
              <div className="text-[11px] font-semibold uppercase tracking-wide text-gray-500">
                Starting lineup
              </div>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {preview.config.roster
                  .filter((s) => !s.bench)
                  .map((s) => (
                    <span
                      key={s.name}
                      className="rounded border border-white/10 bg-white/[0.03] px-2 py-1 text-xs text-gray-300"
                      title={s.eligible.join(" / ")}
                    >
                      {s.count}× {s.name}
                    </span>
                  ))}
                {preview.config.roster
                  .filter((s) => s.bench)
                  .map((s) => (
                    <span
                      key={s.name}
                      className="rounded border border-white/5 bg-white/[0.02] px-2 py-1 text-xs text-gray-500"
                    >
                      {s.count}× {s.name}
                    </span>
                  ))}
              </div>
            </div>
          </div>

          {/* ── things we could not do, said out loud ───────────────────────────────────── */}
          {preview.warnings.length > 0 && (
            <div className="mt-4 rounded-lg border border-amber-500/30 bg-amber-500/5 p-4">
              <div className="flex items-center gap-1.5 text-xs font-semibold text-amber-400">
                <AlertTriangle className="h-3.5 w-3.5" /> What we could not read exactly
              </div>
              <ul className="mt-2 space-y-1.5 text-xs text-gray-300">
                {preview.warnings.map((w, i) => (
                  <li key={i}>• {w}</li>
                ))}
              </ul>
            </div>
          )}

          {/* ── honest coverage, the same machinery the manual editor uses ──────────────── */}
          {coverage && (
            <>
              {/* NF-C0d — the aggregate coverage-gap disclosure. Says WHAT we record (a setting
                  and its point value) and WHY (to know which gaps to close), never buried in a
                  policy page — see recordCapturedTermTelemetry for what actually gets sent. */}
              <p className="mt-4 text-[11px] text-gray-500">
                We record which settings we could not apply — the rule and its point value only,
                never your name, team or roster — so we know which gaps to close next.
              </p>
              <div className="mt-2 grid gap-3 sm:grid-cols-3">
                {(["applied", "derived", "captured"] as const).map((verdict) => {
                  const terms = byVerdict(verdict)
                  return (
                    <div
                      key={verdict}
                      className={`rounded-lg border p-3 ${VERDICT_STYLE[verdict]}`}
                    >
                      <div className="text-xs font-semibold capitalize">
                        {verdict} · {terms.length}
                      </div>
                      <p className="mt-1 text-[11px] opacity-80">{VERDICT_COPY[verdict]}</p>
                      {terms.length > 0 && (
                        <div className="mt-2 max-h-40 overflow-y-auto text-[11px] opacity-90">
                          {terms.map((t) => (
                            <div key={t.key} className="flex justify-between gap-2 py-0.5">
                              {/* ESPN numbers its scoring rules, so a captured key renders as
                                  "129@dst" unless the server sends a label. `?? t.key` keeps a
                                  missing label a cosmetic fallback rather than a blank row. */}
                              <span className="truncate" title={t.key}>
                                {preview.unmapped_labels?.[t.key] ?? t.key}
                              </span>
                              <span className="shrink-0 tabular-nums">{num(t.weight, 2)}</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            </>
          )}

          {/* ── live draft state ────────────────────────────────────────────────────────── */}
          {preview.draft && (
            <div className="mt-4 rounded-lg border border-white/10 bg-white/[0.02] p-4">
              <div className="text-[11px] font-semibold uppercase tracking-wide text-gray-500">
                Draft
              </div>
              {preview.draft.pick_count > 0 ? (
                <>
                  <p className="mt-1 text-xs text-gray-400">
                    {preview.draft.pick_count} pick{preview.draft.pick_count === 1 ? "" : "s"} made
                    {preview.draft.status ? ` · ${preview.draft.status}` : ""}
                    {preview.draft.rounds ? ` · ${preview.draft.rounds} rounds` : ""}
                  </p>
                  {/* ⚠️ read fresh every time this page loads — never stored with the league. A
                      stale "already drafted" list looks exactly like a correct one. */}
                  <p className="mt-1 text-[11px] text-gray-600">
                    Draft state is read live from {preview.platform === "yahoo" ? "Yahoo" : "Sleeper"}{" "}
                    each time, never saved, so it cannot go stale.
                  </p>
                  <div className="mt-2 flex flex-wrap gap-1">
                    {preview.draft.picks.slice(-14).map((p) => (
                      <span
                        key={p.pick_no}
                        className="rounded border border-white/10 px-1.5 py-0.5 text-[10px] text-gray-400"
                      >
                        {p.pick_no}. {p.player?.name ?? "—"}
                      </span>
                    ))}
                  </div>
                </>
              ) : (
                <p className="mt-1 text-xs text-gray-500">
                  {preview.draft.note || "No picks yet."}
                </p>
              )}
            </div>
          )}

          {/* ── teams ───────────────────────────────────────────────────────────────────── */}
          {preview.teams.length > 0 && (
            <div className="mt-4 rounded-lg border border-white/10 bg-white/[0.02] p-4">
              <div className="text-[11px] font-semibold uppercase tracking-wide text-gray-500">
                Teams · {preview.teams.length}
              </div>
              <p className="mt-1 text-[11px] text-gray-600">
                Click a team to see its roster.{" "}
                {preview.teams.some((t) => t.is_owner)
                  ? "We've marked which one is yours below — change it if we got it wrong."
                  : "This platform does not tell us which team is yours, so pick it below — that " +
                    "is what lets My Teams show your roster's projection."}
              </p>
              <div className="mt-2 space-y-1.5">
                {preview.teams.map((t) => {
                  const isOpen = expandedTeams.has(t.team_key)
                  const isMine = selectedTeamKey === t.team_key
                  return (
                    <div
                      key={t.team_key}
                      className={`rounded border ${isMine ? "border-emerald-500/40" : "border-white/10"}`}
                    >
                      <div className="flex w-full items-center gap-2 px-2 py-1">
                        <button
                          type="button"
                          onClick={() => setSelectedTeamKey(isMine ? null : t.team_key)}
                          title={isMine ? "Unmark as your team" : "This is my team"}
                          className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium ${
                            isMine
                              ? "bg-emerald-500/15 text-emerald-300"
                              : "bg-white/[0.03] text-gray-500 hover:text-gray-300"
                          }`}
                        >
                          {isMine ? "✓ Mine" : "Mine?"}
                        </button>
                        <button
                          type="button"
                          onClick={() =>
                            setExpandedTeams((prev) => {
                              const next = new Set(prev)
                              if (next.has(t.team_key)) next.delete(t.team_key)
                              else next.add(t.team_key)
                              return next
                            })
                          }
                          className="flex flex-1 items-center justify-between text-left text-[11px] text-gray-400 hover:bg-white/[0.03]"
                        >
                          <span>
                            {t.name}
                            {t.owner ? ` · ${t.owner}` : ""} ({t.players.length})
                          </span>
                        </button>
                      </div>
                      {isOpen && (
                        <div className="flex flex-wrap gap-1 border-t border-white/5 p-2">
                          {t.players.length === 0 && (
                            <span className="text-[11px] text-gray-600">No players on this roster.</span>
                          )}
                          {t.players.map((p) => (
                            <span
                              key={p.player_key}
                              title={p.position ? `${p.position}${p.team ? ` · ${p.team}` : ""}` : undefined}
                              className={`rounded px-1.5 py-0.5 text-[10px] ${
                                p.starter
                                  ? "bg-emerald-500/10 text-emerald-300"
                                  : "bg-white/[0.03] text-gray-500"
                              }`}
                            >
                              {/* An id we could not resolve to a name still shows honestly — as its
                                  Sleeper id — rather than being hidden (NF-C0c). */}
                              {p.name || `#${p.player_key}`}
                              {p.position ? ` · ${p.position}` : ""}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* 🚩 Yahoo's API terms require this attribution wherever their data is shown. */}
          {preview.platform === "yahoo" && (
            <p className="mt-4 text-[11px] text-gray-600">
              <a
                href="https://football.fantasysports.yahoo.com/"
                target="_blank"
                rel="noreferrer"
                className="hover:underline"
              >
                Fantasy data provided by Yahoo Fantasy
              </a>
            </p>
          )}
        </section>
      )}
    </div>
  )
}

function Banner({ tone, children }: { tone: "ok" | "warn"; children: React.ReactNode }) {
  const style =
    tone === "ok"
      ? "border-emerald-500/30 bg-emerald-500/5 text-emerald-300"
      : "border-amber-500/30 bg-amber-500/5 text-amber-300"
  return <div className={`mt-4 rounded-lg border px-4 py-2 text-xs ${style}`}>{children}</div>
}
