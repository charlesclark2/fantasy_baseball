import Link from "next/link"
import { Nav } from "@/components/nav"
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion"
import { FAQ_HEADER, FAQ_SECTIONS } from "@/lib/positioning-copy"

/**
 * E9.60 — the FAQ, brought into alignment with the live home-page positioning.
 *
 * ══ WHAT WAS WRONG ═════════════════════════════════════════════════════════════════════════════
 *
 * The page answered "What sport(s) does Credence cover?" with "MLB baseball only, for the 2026
 * season", called the company "a baseball analytics tool", and had no fantasy section at all — the
 * same two sentences E9.46 had already had to delete from the landing FAQ, still live one route
 * over. It also named Bovada as "the benchmark we use for edge detection", conflating the de-vigged
 * consensus we compare against with the book whose price a pick is graded at.
 *
 * ⛔ AND IT TOLD VISITORS HOW MUCH TO BET. "What is Kelly % and how much should I bet?" is gone:
 * stake sizing presumes something to size against, and `best_alpha = 0` says we do not have it
 * (spec §18.9). ⚠️ The FEATURE is still live behind the paywall — `/ev-tracker` renders raw and
 * capped Kelly columns and `/settings` carries a Kelly cap — and removing it is a product decision
 * outside this story's scope. It is flagged in the handoff rather than half-done here.
 *
 * ══ THE SHAPE ══════════════════════════════════════════════════════════════════════════════════
 *
 * Four sections in the site's one product order (spec §17): About Credence → Fantasy football →
 * Betting intelligence → Trust and methodology.
 *
 * ⛔ Every answer lives in `lib/positioning-copy.ts` and is screened by
 * `betting_ml/tests/test_e9_60_positioning_copy.py`. An answer needing an anchor carries a `link`
 * field rather than becoming JSX — the pre-E9.60 page had exactly one JSX answer and it was the one
 * no denylist could read.
 *
 * ⭐ THIS PAGE IS STATIC — no read at request time.
 */

export const metadata = {
  title: "FAQ — Credence Sports",
  description: FAQ_HEADER.subhead,
}

export default function FaqPage() {
  return (
    <div className="min-h-screen bg-background flex flex-col">
      <Nav />

      <main className="flex-1 mx-auto w-full max-w-3xl px-6 py-12">
        <div className="mb-10">
          <p className="text-xs uppercase tracking-widest text-muted-foreground mb-1">
            {FAQ_HEADER.eyebrow}
          </p>
          <h1 className="text-3xl font-bold text-foreground">{FAQ_HEADER.heading}</h1>
          <p className="mt-3 text-sm text-gray-400 leading-relaxed">{FAQ_HEADER.subhead}</p>
          <p className="mt-2 text-sm text-muted-foreground">
            Can&apos;t find what you&apos;re looking for?{" "}
            <Link href="/contact" className="text-[#10b981] hover:underline">
              Contact us
            </Link>
            .
          </p>
        </div>

        <div className="space-y-10">
          {FAQ_SECTIONS.map((section) => (
            <div key={section.category} data-faq-section={section.category}>
              <h2 className="text-xs uppercase tracking-widest text-muted-foreground mb-4">
                {section.category}
              </h2>
              <Accordion type="multiple" className="space-y-1">
                {section.items.map((item) => (
                  <AccordionItem
                    key={item.q}
                    value={item.q}
                    className="border border-[#262626] rounded-md px-4"
                  >
                    <AccordionTrigger className="text-sm font-medium text-gray-200 hover:text-white py-4 text-left">
                      {item.q}
                    </AccordionTrigger>
                    <AccordionContent className="text-sm text-gray-400 leading-relaxed pb-4">
                      {item.a}
                      {item.link && (
                        <span className="mt-3 block">
                          {/* A `mailto:` is not a route, so it stays a plain anchor — `<Link>`
                              would be wrong and E9.56c's route guard only reads `href="/…"`. */}
                          {item.link.href.startsWith("/") ? (
                            <Link
                              href={item.link.href}
                              className="text-[#10b981] hover:underline"
                            >
                              {item.link.label} →
                            </Link>
                          ) : (
                            <a
                              href={item.link.href}
                              className="text-[#10b981] hover:underline"
                            >
                              {item.link.label}
                            </a>
                          )}
                        </span>
                      )}
                    </AccordionContent>
                  </AccordionItem>
                ))}
              </Accordion>
            </div>
          ))}
        </div>

        <div className="mt-12 pt-8 border-t border-[#262626] flex flex-wrap gap-6 text-sm text-muted-foreground">
          <Link href="/about" className="hover:text-foreground transition-colors">
            About
          </Link>
          {/* ⭐ The evidence, one click away. NF-TR1's rule for a marketing surface: link to the
              record rather than quoting its number. The literal href also keeps this inside
              `test_e9_56c_cta_routes.py`'s static route scan, which the answers' data-driven
              `item.link` anchors are outside of. */}
          <Link href="/fantasy/track-record" className="hover:text-foreground transition-colors">
            Track Record
          </Link>
          <Link href="/contact" className="hover:text-foreground transition-colors">
            Contact
          </Link>
          <Link href="/privacy" className="hover:text-foreground transition-colors">
            Privacy Policy
          </Link>
          <Link href="/terms" className="hover:text-foreground transition-colors">
            Terms of Service
          </Link>
        </div>
      </main>
    </div>
  )
}
