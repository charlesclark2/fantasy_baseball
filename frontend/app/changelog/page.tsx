import { Nav } from "@/components/nav"
import changelog from "@/data/changelog.json"

export const metadata = {
  title: "Changelog — Credence Sports",
}

const TAG_STYLES: Record<string, string> = {
  new: "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20",
  improvement: "bg-blue-500/10 text-blue-400 border border-blue-500/20",
  fix: "bg-amber-500/10 text-amber-400 border border-amber-500/20",
  model: "bg-purple-500/10 text-purple-400 border border-purple-500/20",
  data: "bg-gray-500/10 text-gray-400 border border-gray-500/20",
}

function formatWeek(week: string) {
  const start = new Date(week + "T00:00:00")
  const end = new Date(week + "T00:00:00")
  end.setUTCDate(end.getUTCDate() + 6)
  const rangeOpts: Intl.DateTimeFormatOptions = { month: "long", day: "numeric", timeZone: "UTC" }
  const endOpts: Intl.DateTimeFormatOptions = { month: "long", day: "numeric", year: "numeric", timeZone: "UTC" }
  return `${start.toLocaleDateString("en-US", rangeOpts)} – ${end.toLocaleDateString("en-US", endOpts)}`
}

export default function ChangelogPage() {
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

        <div className="space-y-12">
          {changelog.map((entry) => (
            <div key={entry.week}>
              <h2 className="text-xs uppercase tracking-widest text-muted-foreground mb-4">
                Week of {formatWeek(entry.week)}
              </h2>
              <ul className="space-y-3">
                {entry.items.map((item, i) => (
                  <li key={i} className="flex items-start gap-3">
                    <span
                      className={`mt-0.5 shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${
                        TAG_STYLES[item.tag] ?? TAG_STYLES.data
                      }`}
                    >
                      {item.tag}
                    </span>
                    <span className="text-sm text-gray-300 leading-relaxed">
                      {item.text}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

      </main>
    </div>
  )
}
