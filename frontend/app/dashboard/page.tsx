import { PicksTable } from "@/components/picks-table"
import { Calendar, TrendingUp } from "lucide-react"

function formatDate(date: Date) {
  return date.toLocaleDateString("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
  })
}

export default function DashboardPage() {
  const today = new Date()
  const qualifiedCount = 3
  const totalGames = 8

  return (
    <div className="min-h-screen">
      {/* Header */}
      <header className="border-b border-border/50 bg-card/30 backdrop-blur-sm sticky top-0 z-10">
        <div className="container mx-auto px-4 py-4 sm:py-6">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            {/* Logo & Date */}
            <div className="space-y-1">
              <h1 className="text-xl sm:text-2xl font-bold tracking-tight flex items-center gap-2">
                <span className="text-emerald-400">◆</span>
                Credence Sports
              </h1>
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Calendar className="h-4 w-4" />
                <span>{formatDate(today)}</span>
              </div>
            </div>

            {/* Stats */}
            <div className="flex items-center gap-3 sm:gap-4">
              <div className="flex items-center gap-2 rounded-lg bg-emerald-500/10 border border-emerald-500/20 px-3 py-2">
                <TrendingUp className="h-4 w-4 text-emerald-400" />
                <span className="text-sm font-medium">
                  <span className="text-emerald-400">{qualifiedCount} qualified picks</span>
                </span>
              </div>
              <div className="text-sm text-muted-foreground">
                {totalGames} total games today
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="container mx-auto px-4 py-6 sm:py-8">
        <div className="mb-6">
          <h2 className="text-lg font-semibold mb-1">Today&apos;s Picks</h2>
          <p className="text-sm text-muted-foreground">
            Qualified picks meet minimum edge and conviction thresholds
          </p>
        </div>

        <PicksTable />

        {/* Legend - visible on mobile to explain hidden columns */}
        <div className="mt-6 rounded-lg border bg-card/50 p-4 sm:hidden">
          <p className="text-xs text-muted-foreground mb-2 font-medium uppercase tracking-wider">
            Legend
          </p>
          <div className="space-y-2 text-sm text-muted-foreground">
            <p>
              <span className="text-emerald-400 font-mono">Edge</span> = Model % − Bovada %
            </p>
            <p>
              <span className="text-emerald-400/70 border-l-2 border-l-emerald-500/70 pl-2">
                Green border
              </span>{" "}
              = Qualified pick
            </p>
          </div>
        </div>
      </main>
    </div>
  )
}
