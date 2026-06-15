"use client"

import Link from "next/link"
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion"

const LANDING_FAQ = [
  {
    q: "What does Credence Sports actually do?",
    a: "Credence is a baseball analytics tool, not a picks service. We build statistical models that estimate the true probability of game outcomes, then compare those estimates against the betting market to identify where the odds may be mispriced. You see the analysis — you decide what to do with it.",
  },
  {
    q: "Is this automated betting?",
    a: "No. Automated bet placement is not possible in the US market. Every wager is your own manual decision. Credence provides analysis and signals; nothing is ever placed on your behalf.",
  },
  {
    q: "What does Expected Value (EV) mean?",
    a: "EV measures whether a bet is priced in your favor over time. Positive EV means our model estimates the true probability of winning is higher than what the sportsbook's odds imply. It doesn't guarantee a win on any single bet — it means the math favors you across many similar bets.",
  },
  {
    q: "What's the difference between Model % and Market %?",
    a: "Model % is the probability our model assigns to an outcome. Market % is the implied probability from the current odds after removing the sportsbook's margin. When Model % is meaningfully higher than Market %, that's where a pick comes from.",
  },
  {
    q: "Which sportsbooks does Credence target?",
    a: "Our models are calibrated and compared against Bovada lines. If you use a different sportsbook, the displayed odds will differ and the calculated EV may not apply directly.",
  },
  {
    q: "What sport(s) does Credence cover?",
    a: "MLB baseball only, for the 2026 season. We're focused on doing one sport well before expanding.",
  },
]

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
