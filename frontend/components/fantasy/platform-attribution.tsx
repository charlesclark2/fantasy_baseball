/**
 * NF-C0-Yahoo-ENABLE (Half A) — the platform attribution, in ONE place.
 *
 * 🚩 A CONTRACTUAL REQUIREMENT, NOT DECORATION. Yahoo's API terms (Cover / §5) require
 * "Fantasy data provided by Yahoo Fantasy", hyperlinked back to Yahoo Fantasy, to be displayed
 * WHEREVER their data is shown. The spike memo measured us rendering it in exactly one place — the
 * import PREVIEW, before the league is even saved (`league-import.tsx`) — while every surface that
 * shows the data AFTER it is saved showed none. That was gap B3.
 *
 * ⭐ WHY A COMPONENT RATHER THAN SEVEN COPIES OF THE STRING. Seven copies is seven rule sets: the
 * next surface that renders an imported league is one that quietly ships without it, and the
 * failure is INVISIBLE from every instrument we own — the page renders, the tests pass, and the
 * only signal is a compliance breach nobody can see (E9.61, "two renderers of one field are two
 * rule sets"). One component keyed on `source_platform` means adding a surface is adding a call,
 * and adding a PLATFORM that requires attribution is adding a row to `PLATFORM_ATTRIBUTION` below.
 *
 * ⚠️ KEYED ON THE LEAGUE'S OWN PROVENANCE, never on which page you are on. A surface showing a
 * Sleeper or hand-entered league renders nothing; a surface showing several leagues renders one
 * line per attributed platform present. That is what makes the call site impossible to get subtly
 * wrong — the caller passes what it is displaying and the rule lives here.
 */
/** The platforms whose terms require an on-screen credit, and the exact wording each requires.
 *
 *  ⚠️ Mirrors `app/backend/services/platform_import/yahoo.py::ATTRIBUTION` / `ATTRIBUTION_URL`
 *  (the server also serves them on `GET /fantasy/import/platforms`). Sleeper's and ESPN's terms
 *  carry no equivalent requirement today, so they are deliberately ABSENT rather than present with
 *  an empty string — a row here is a statement that a credit is owed. */
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
 *  nothing to do with attribution. The minimal shape is also the honest one: this component needs
 *  exactly one field. */
export type AttributionSource = string | null | undefined | { source_platform?: string | null }

/** The distinct platforms among `sources` that owe an attribution, in a stable order.
 *
 *  Exported so a test can assert the RULE independently of the markup, and so a caller that needs
 *  to place the credit itself (the import preview renders it inside its own review panel) resolves
 *  it the same way rather than re-deriving "is this Yahoo?" a second time. */
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

/**
 * The credit line. Renders nothing when nothing on screen owes one.
 *
 * `data-testid="platform-attribution"` is what the E2E asserts on — the RENDERED output, because a
 * source grep would be satisfied by a string that no branch ever reaches (NF-C4).
 */
export function PlatformAttribution({
  sources,
  className = "",
}: {
  sources: AttributionSource | AttributionSource[]
  className?: string
}) {
  const platforms = attributedPlatforms(sources)
  if (platforms.length === 0) return null
  return (
    <p
      data-testid="platform-attribution"
      className={`mt-4 text-[11px] text-gray-600 ${className}`.trim()}
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
