"use client"

/**
 * The platform attribution, in ONE place — and, since the clause audit, IN THE PAGE FOOTER.
 *
 * 🚩 WHAT THE AGREEMENT ACTUALLY SAYS (Cover Page, "Attribution"), now that we have read it:
 *
 *   "Developer must provide clear attribution to Yahoo Fantasy wherever Yahoo Fantasy Information
 *    is displayed (i.e., 'Fantasy data provided by Yahoo Fantasy') … Web — For websites and
 *    web-based Developer Applications, attribution must appear IN THE FOOTER OF EACH PAGE where
 *    Yahoo Fantasy Information is displayed and must include a hyperlink to an official Yahoo
 *    Fantasy webpage."
 *
 * ⚠️ NF-C0-Yahoo-ENABLE Half A shipped this at the END OF EACH SURFACE'S MAIN CONTENT, which sits
 * ABOVE the site footer rather than in it. That was written against the spike memo's paraphrase
 * ("attribution + hyperlink on every page showing Yahoo data") — the clause text was not available
 * at the time and the memo did not carry the word "footer". The requirement is more specific than
 * the paraphrase, so the credit now renders inside `SiteFooter`'s `<footer>` element.
 *
 * ══ HOW A PAGE-LEVEL FACT REACHES A ROOT-LAYOUT FOOTER ════════════════════════════════════════
 *
 * `SiteFooter` is a SIBLING of `{children}` in `app/layout.tsx`, so no page can render into it
 * directly (the same structural fact NF-C4 hit from the other side, where no page-level
 * `print:hidden` could reach the footer). Whether Yahoo data is on screen is a per-page,
 * client-data fact, so it is REGISTERED here and READ in the footer:
 *
 *   · a surface renders `<PlatformAttribution sources={…} />`, which draws nothing and registers
 *     the platforms its data came from;
 *   · `<PlatformAttributionFooterSlot />`, inside `SiteFooter`, renders the credit for whatever is
 *     currently registered.
 *
 * ⭐ TWO CONTEXTS, NOT ONE, AND THE SPLIT IS LOAD-BEARING. The registering component consumes only
 * the ACTIONS context, whose value never changes. A single context carrying both the actions and
 * the platform list would change identity on every registration, so the registering effect would
 * re-run, its cleanup would UNREGISTER, that would change the value again, and the two would flip
 * back and forth forever. It renders as a hung tab, not as a wrong credit.
 *
 * ⭐ AND IT FAILS SAFE: with no provider above it (a tree that somehow bypasses the root layout)
 * the component renders the credit INLINE instead of registering it. The failure this whole module
 * exists to prevent is a credit that silently is not there, so "no provider" must not be a way to
 * reach that state quietly.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useId,
  useMemo,
  useState,
} from "react"

/** The platforms whose terms require an on-screen credit, and the exact wording each requires.
 *
 *  ⚠️ Mirrors `app/backend/services/platform_import/yahoo.py::ATTRIBUTION` / `ATTRIBUTION_URL`
 *  (the server also serves them on `GET /fantasy/import/platforms`), pinned equal by
 *  `betting_ml/tests/test_nf_c0_yahoo_halfa_compliance.py`. Sleeper's and ESPN's terms carry no
 *  equivalent requirement today, so they are deliberately ABSENT rather than present with an empty
 *  string — a row here is a statement that a credit is owed. */
export const PLATFORM_ATTRIBUTION: Record<string, { text: string; href: string }> = {
  yahoo: {
    text: "Fantasy data provided by Yahoo Fantasy",
    href: "https://football.fantasysports.yahoo.com/",
  },
}

/** Anything a surface might have on screen: a platform id, a league, or a list of either.
 *
 *  ⚠️ STRUCTURAL, not `Pick<SavedLeague, …> & Record<string, unknown>`. A TS interface carries no
 *  implicit index signature, so intersecting with `Record<string, unknown>` makes every real
 *  `SavedLeague` UNASSIGNABLE — the call sites would all fail to compile for a reason that has
 *  nothing to do with attribution. The minimal shape is also the honest one: this needs one field. */
export type AttributionSource = string | null | undefined | { source_platform?: string | null }

/** The distinct platforms among `sources` that owe an attribution, in a stable order. */
export function attributedPlatforms(
  sources: AttributionSource | AttributionSource[],
): string[] {
  const list: AttributionSource[] = Array.isArray(sources) ? sources : [sources]
  const seen: string[] = []
  for (const entry of list) {
    if (!entry) continue
    const raw = typeof entry === "string" ? entry : entry.source_platform
    const key = String(raw ?? "").trim().toLowerCase()
    if (!key || !PLATFORM_ATTRIBUTION[key] || seen.includes(key)) continue
    seen.push(key)
  }
  return seen
}

interface Actions {
  register: (id: string, platforms: string[]) => void
  unregister: (id: string) => void
}

/** Stable for the lifetime of the provider — see the module header for why that matters. */
const ActionsContext = createContext<Actions | null>(null)
/** Changes as surfaces mount and unmount. Consumed ONLY by the footer slot. */
const PlatformsContext = createContext<string[]>([])

const sameList = (a: string[] | undefined, b: string[]) =>
  !!a && a.length === b.length && a.every((v, i) => v === b[i])

export function PlatformAttributionProvider({ children }: { children: React.ReactNode }) {
  const [registry, setRegistry] = useState<Record<string, string[]>>({})

  const register = useCallback((id: string, platforms: string[]) => {
    // Functional update + an equality guard: re-registering the same platforms must not produce a
    // new state object, or every consumer re-renders on every commit for no change.
    setRegistry((prev) => (sameList(prev[id], platforms) ? prev : { ...prev, [id]: platforms }))
  }, [])

  const unregister = useCallback((id: string) => {
    setRegistry((prev) => {
      if (!(id in prev)) return prev
      const next = { ...prev }
      delete next[id]
      return next
    })
  }, [])

  const actions = useMemo<Actions>(() => ({ register, unregister }), [register, unregister])
  const platforms = useMemo(() => {
    const seen: string[] = []
    for (const list of Object.values(registry)) {
      for (const key of list) if (!seen.includes(key)) seen.push(key)
    }
    return seen
  }, [registry])

  return (
    <ActionsContext.Provider value={actions}>
      <PlatformsContext.Provider value={platforms}>{children}</PlatformsContext.Provider>
    </ActionsContext.Provider>
  )
}

/**
 * Declare that this surface is displaying data from `sources`. Draws nothing itself.
 *
 * ⚠️ Callers pass what they are DISPLAYING; the rule for what that owes lives here. That is what
 * makes a call site impossible to get subtly wrong, and it is why adding a surface is adding a
 * call rather than copying a string (E9.61 — two renderers of one field are two rule sets).
 */
export function PlatformAttribution({
  sources,
  className = "",
}: {
  sources: AttributionSource | AttributionSource[]
  className?: string
}) {
  const actions = useContext(ActionsContext)
  const id = useId()
  const platforms = attributedPlatforms(sources)
  // A primitive dep, so the effect re-runs when the SET changes rather than on every render (a
  // fresh array literal is a new reference every time).
  const key = platforms.join("|")

  useEffect(() => {
    if (!actions) return
    actions.register(id, key ? key.split("|") : [])
    return () => actions.unregister(id)
  }, [actions, id, key])

  // The fail-safe path only — see the module header. With a provider present this draws nothing and
  // the footer carries the credit, which is what the Cover Page requires.
  if (actions) return null
  return <AttributionLine platforms={platforms} className={className} />
}

/**
 * The credit itself, rendered inside `SiteFooter`'s `<footer>`.
 *
 * `data-testid="platform-attribution"` is what the E2E asserts on — the RENDERED output, because a
 * source grep would be satisfied by a string that no branch ever reaches (NF-C4).
 */
export function PlatformAttributionFooterSlot({ className = "" }: { className?: string }) {
  return <AttributionLine platforms={useContext(PlatformsContext)} className={className} />
}

function AttributionLine({ platforms, className }: { platforms: string[]; className: string }) {
  if (platforms.length === 0) return null
  return (
    <p
      data-testid="platform-attribution"
      className={`text-[11px] text-gray-500 ${className}`.trim()}
    >
      {platforms.map((key, i) => {
        const { text, href } = PLATFORM_ATTRIBUTION[key]
        return (
          <span key={key}>
            {i > 0 ? " · " : ""}
            <a href={href} target="_blank" rel="noreferrer" className="hover:underline">
              {text}
            </a>
          </span>
        )
      })}
    </p>
  )
}
