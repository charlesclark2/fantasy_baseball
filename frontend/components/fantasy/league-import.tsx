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
import { useSearchParams } from "next/navigation"
import {
  AlertTriangle,
  ArrowRight,
  Check,
  Download,
  Link2,
  Loader2,
  Unlink,
} from "lucide-react"
import { useAuth } from "@/lib/auth-context"
import { useFantasyProjections, useSaveLeague, useSavedLeagues } from "@/lib/fantasy-queries"
import {
  listImportPlatforms,
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
import { EmptyBlock, LoadingBlock, SurfaceHeader, num } from "@/components/fantasy/shared"

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
  const { accessToken } = useAuth()
  const search = useSearchParams()
  const saveLeague = useSaveLeague()
  const { data: savedLeagues } = useSavedLeagues()
  const { data: projections } = useFantasyProjections()

  const [platforms, setPlatforms] = useState<ImportPlatform[] | null>(null)
  const [platformId, setPlatformId] = useState<string>("sleeper")
  const [username, setUsername] = useState("")
  const [leagues, setLeagues] = useState<PlatformLeagueSummary[] | null>(null)
  const [preview, setPreview] = useState<ImportPreview | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState<string | null>(null)

  // The Yahoo callback returns the browser here with a status flag rather than a JSON body — the
  // user is mid-flow in a browser, so the outcome has to be visible on the page they land on.
  const yahooFlag = search.get("yahoo")

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

  async function connectYahoo() {
    const res = await run("yahoo-connect", () => yahooAuthorizeUrl(accessToken))
    if (res?.authorize_url) window.location.href = res.authorize_url
  }

  async function loadYahooLeagues() {
    setPreview(null)
    const res = await run("yahoo-leagues", () => yahooLeagues(accessToken))
    if (res) setLeagues(res.leagues)
  }

  async function loadPreview(leagueId: string) {
    const res = await run("preview", () =>
      platformId === "yahoo"
        ? yahooPreview(accessToken, leagueId)
        : sleeperPreview(accessToken, leagueId),
    )
    if (res) {
      setPreview(res)
      setSaved(null)
    }
  }

  async function saveImported() {
    if (!preview) return
    // Re-importing a league you already saved UPDATES it rather than creating a duplicate. Two
    // copies of the same league is a silent trap: the user edits one and the board reads the other.
    const already = (savedLeagues ?? []).find(
      (l) =>
        l.source_platform === preview.platform &&
        l.source_league_id === preview.source_league_id,
    )
    const payload: LeagueSaveInput = {
      ...preview.config,
      source_platform: preview.platform,
      source_league_id: preview.source_league_id,
      imported_at: new Date().toISOString(),
    }
    const res = await run("save", () =>
      saveLeague.mutateAsync({ leagueId: already?.league_id ?? null, config: payload }),
    )
    if (res) setSaved(already ? "updated" : "saved")
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

      {/* ⛔ ESPN. Stated plainly rather than omitted: ESPN is the biggest platform, so a user who
          does not see it will assume the feature is broken. Naming the reason — and pointing at the
          floor that already works — is the honest version. */}
      <p className="mt-3 text-xs text-gray-500">
        <span className="text-gray-400">ESPN is not listed.</span> ESPN publishes no approved way for
        another app to read a private league — the only route would be handling your ESPN login
        session, and we will not do that. If your league is on ESPN (or CBS, MFL or Fantrax), enter it
        once under{" "}
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
          <div className="mt-3 flex flex-wrap items-center gap-2">
            {/* text-base on phones (iOS auto-zooms on focus below 16px), text-sm from sm: up. */}
            <input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && username.trim() && void findSleeperLeagues()}
              placeholder="Sleeper username or league ID"
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
              Find league
            </button>
            <span className="text-xs text-gray-500">
              Your league ID is the long number in your league&apos;s Sleeper URL
              (sleeper.app/leagues/<span className="text-gray-400">1234567890123456789</span>/…).
              Sleeper&apos;s league data is public — no sign-in needed.
            </span>
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
          <div className="mt-4 divide-y divide-white/5 rounded-lg border border-white/10">
            {leagues.map((l) => (
              <button
                key={l.league_id}
                onClick={() => void loadPreview(l.league_id)}
                className="flex w-full items-center justify-between px-4 py-3 text-left hover:bg-white/[0.03]"
              >
                <div>
                  <div className="text-sm text-gray-100">{l.name}</div>
                  <div className="text-xs text-gray-500">
                    {l.total_rosters || "?"}-team · {l.season}
                    {l.status ? ` · ${l.status.replace(/_/g, " ")}` : ""}
                  </div>
                </div>
                {busy === "preview" ? (
                  <Loader2 className="h-4 w-4 animate-spin text-gray-500" />
                ) : (
                  <ArrowRight className="h-4 w-4 text-gray-500" />
                )}
              </button>
            ))}
          </div>
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
                disabled={busy === "save"}
                className="flex items-center gap-1.5 rounded bg-emerald-600 px-3 py-2 text-sm font-medium text-white disabled:opacity-40"
              >
                {busy === "save" ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Download className="h-3.5 w-3.5" />
                )}
                Save this league
              </button>
            </div>

            {saved && (
              <p className="mt-3 text-xs text-emerald-400">
                League {saved}. It now appears everywhere you pick a format — rankings, the board and
                the draft optimizer.
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
            <div className="mt-4 grid gap-3 sm:grid-cols-3">
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
                            <span className="truncate">{t.key}</span>
                            <span className="shrink-0 tabular-nums">{num(t.weight, 2)}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
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
              <div className="mt-2 flex flex-wrap gap-1.5">
                {preview.teams.map((t) => (
                  <span
                    key={t.team_key}
                    className="rounded border border-white/10 px-2 py-1 text-[11px] text-gray-400"
                  >
                    {t.name}
                    {t.owner ? ` · ${t.owner}` : ""} ({t.players.length})
                  </span>
                ))}
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
