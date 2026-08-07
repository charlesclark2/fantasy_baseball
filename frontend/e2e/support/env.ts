import { readFileSync } from "node:fs"
import { join } from "node:path"

/**
 * Read the build-time environment the app under test was COMPILED with (`e2e/e2e.env`).
 *
 * `NEXT_PUBLIC_*` values are inlined at build time and are NOT present in the Playwright process,
 * so a spec cannot simply read `process.env` to learn what the app was configured with. Reading
 * the same file the build sourced is what makes "the app used the host it was given" a real
 * cross-check rather than a tautology — the first cut of the Google-redirect assertion compared
 * the URL's host against `process.env.… ?? url.host`, which passes for every possible value.
 */
const ENV_FILE = join(process.cwd(), "e2e", "e2e.env")

let cache: Record<string, string> | null = null

function load(): Record<string, string> {
  if (cache) return cache
  const out: Record<string, string> = {}
  for (const line of readFileSync(ENV_FILE, "utf8").split("\n")) {
    const trimmed = line.trim()
    if (!trimmed || trimmed.startsWith("#")) continue
    const eq = trimmed.indexOf("=")
    if (eq < 0) continue
    out[trimmed.slice(0, eq)] = trimmed.slice(eq + 1)
  }
  cache = out
  return out
}

/** A required build-time value. Throws rather than returning undefined — a spec that silently
 *  compares against `undefined` is the vacuous assertion this module exists to prevent. */
export function buildEnv(key: string): string {
  const value = load()[key]
  if (!value) throw new Error(`e2e/e2e.env has no non-empty ${key}`)
  return value
}
