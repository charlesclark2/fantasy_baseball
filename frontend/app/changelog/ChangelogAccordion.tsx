"use client"

import { useState } from "react"
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion"

const TAG_STYLES: Record<string, string> = {
  new: "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20",
  improvement: "bg-blue-500/10 text-blue-400 border border-blue-500/20",
  fix: "bg-amber-500/10 text-amber-400 border border-amber-500/20",
  model: "bg-purple-500/10 text-purple-400 border border-purple-500/20",
  data: "bg-gray-500/10 text-gray-400 border border-gray-500/20",
}

function formatWeek(monday: string): string {
  const start = new Date(monday + "T00:00:00Z")
  const end = new Date(monday + "T00:00:00Z")
  end.setUTCDate(end.getUTCDate() + 6)
  const rangeOpts: Intl.DateTimeFormatOptions = { month: "long", day: "numeric", timeZone: "UTC" }
  const endOpts: Intl.DateTimeFormatOptions = { month: "long", day: "numeric", year: "numeric", timeZone: "UTC" }
  return `${start.toLocaleDateString("en-US", rangeOpts)} – ${end.toLocaleDateString("en-US", endOpts)}`
}

export type ChangelogEntry = { week: string; items: Array<{ tag: string; text: string }> }

export function ChangelogAccordion({ entries }: { entries: ChangelogEntry[] }) {
  const [openItems, setOpenItems] = useState<string[]>(
    entries.length > 0 ? [entries[0].week] : []
  )
  const allExpanded = entries.length > 0 && openItems.length === entries.length

  return (
    <div>
      {entries.length > 1 && (
        <div className="flex justify-end mb-3">
          <button
            onClick={() => setOpenItems(allExpanded ? [] : entries.map((e) => e.week))}
            className="text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            {allExpanded ? "Collapse all" : "Expand all"}
          </button>
        </div>
      )}
      <Accordion
        type="multiple"
        value={openItems}
        onValueChange={setOpenItems}
        className="space-y-2"
      >
        {entries.map((entry) => (
          <AccordionItem
            key={entry.week}
            value={entry.week}
            className="border border-border rounded-md px-4"
          >
            <AccordionTrigger className="text-xs uppercase tracking-widest text-muted-foreground hover:no-underline py-4">
              <span className="flex items-baseline gap-2">
                <span>Week of {formatWeek(entry.week)}</span>
                <span className="text-[10px] font-normal normal-case tracking-normal text-muted-foreground/50">
                  {entry.items.length} {entry.items.length === 1 ? "update" : "updates"}
                </span>
              </span>
            </AccordionTrigger>
            <AccordionContent>
              <ul className="space-y-3 pt-1 pb-2">
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
            </AccordionContent>
          </AccordionItem>
        ))}
      </Accordion>
    </div>
  )
}
