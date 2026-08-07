"use client"

import Link from "next/link"
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion"

// E9.46 — the questions themselves live in `lib/home-copy.ts`, with every other claim-bearing
// string on this page, so `betting_ml/tests/test_e9_46_home_copy.py` screens them. Inline here
// they were unscreened AND had gone stale ("MLB baseball only") after the NFL launch.
import { LANDING_FAQ } from "@/lib/home-copy"

export function LandingFaqSection() {
  return (
    <section className="py-16 md:py-24 border-t border-[#262626]">
      <div className="mx-auto max-w-3xl px-4">
        <div className="mb-10 flex items-end justify-between">
          <h2 className="text-balance text-2xl font-bold text-white md:text-3xl">
            Common questions
          </h2>
          <Link
            href="/faq"
            className="text-sm text-[#10b981] hover:underline shrink-0 ml-4"
          >
            See all
          </Link>
        </div>
        <Accordion type="multiple" className="space-y-1">
          {LANDING_FAQ.map((item) => (
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
              </AccordionContent>
            </AccordionItem>
          ))}
        </Accordion>
      </div>
    </section>
  )
}
