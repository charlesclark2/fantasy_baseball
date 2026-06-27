import { Nav } from "@/components/nav"
import changelog from "@/data/changelog.json"
import { ChangelogAccordion } from "./ChangelogAccordion"
import type { ChangelogEntry } from "./ChangelogAccordion"

export const metadata = {
  title: "Changelog — Credence Sports",
}

function toMondayUTC(dateStr: string): string {
  const d = new Date(dateStr + "T00:00:00Z")
  const dow = d.getUTCDay() // 0=Sun, 1=Mon, …, 6=Sat
  const daysBack = dow === 0 ? 6 : dow - 1
  d.setUTCDate(d.getUTCDate() - daysBack)
  return d.toISOString().slice(0, 10)
}

function mergeByWeek(): ChangelogEntry[] {
  const map = new Map<string, Array<{ tag: string; text: string }>>()
  for (const entry of changelog) {
    const monday = toMondayUTC(entry.week)
    if (!map.has(monday)) map.set(monday, [])
    map.get(monday)!.push(...entry.items)
  }
  return Array.from(map.entries())
    .sort((a, b) => b[0].localeCompare(a[0]))
    .map(([week, items]) => ({ week, items }))
}

export default function ChangelogPage() {
  const entries = mergeByWeek()
  return (
    <div className="min-h-screen bg-background flex flex-col">
      <Nav />

      <main className="flex-1 mx-auto w-full max-w-3xl px-6 py-12">
        <div className="mb-10">
          <p className="text-xs uppercase tracking-widest text-muted-foreground mb-1">
            Credence Sports · A product of Penumbra Partners
          </p>
          <h1 className="text-3xl font-bold text-foreground">Changelog</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Weekly updates to the platform, models, and data.
          </p>
        </div>

        <ChangelogAccordion entries={entries} />
      </main>
    </div>
  )
}
