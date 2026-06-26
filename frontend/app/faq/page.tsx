import Link from "next/link"
import { Nav } from "@/components/nav"
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion"

export const metadata = {
  title: "FAQ — Credence Sports",
}

const FAQ_SECTIONS = [
  {
    category: "What is Credence Sports?",
    items: [
      {
        q: "What is Bayesian sports analytics?",
        a: "Bayesian analytics treats predictions as probability distributions rather than single point estimates. Instead of outputting just \"62% home win,\" a Bayesian model also quantifies how confident it is in that estimate — and updates that confidence as new information arrives. At Credence, this means predictions tighten as the season progresses and more data accumulates, and uncertainty is carried through the model visibly rather than hidden behind a single number.",
      },
      {
        q: "What does Credence Sports actually do?",
        a: "Credence Sports is a baseball analytics tool. We build statistical models that estimate the true probability of game outcomes and compare those estimates against betting market odds to identify where the market may be mispriced. We surface those findings as picks — but we are an analytics tool, not a picks service. You decide what to do with the information.",
      },
      {
        q: "Is this automated betting?",
        a: "No. Automated bet placement is not possible in the US market. All bets are placed manually by you. Credence provides analysis and signals; every wager is your own decision and your own action.",
      },
      {
        q: "Is sports betting legal?",
        a: "Sports betting laws vary significantly by state. Some states allow online betting through licensed operators; others do not. Credence Sports provides analytics only — we do not provide legal advice and are not a licensed gambling operator. It is your responsibility to understand and comply with the laws in your jurisdiction.",
      },
    ],
  },
  {
    category: "Model & picks",
    items: [
      {
        q: "What does Expected Value (EV) mean and why does it matter?",
        a: "Expected Value (EV) measures whether a bet is priced in your favor over time. A positive EV bet means our model estimates the true probability of winning is higher than what the sportsbook's odds imply. For example, if a team has a 55% chance of winning but the odds only imply a 48% chance, there is positive EV. Positive EV does not guarantee a win on any single bet — it means the math favors you across many similar bets.",
      },
      {
        q: "What's the difference between Model % and Market %?",
        a: "Model % is the probability our model assigns to a specific outcome (e.g., the home team wins). Market % is the implied probability derived from the current betting odds after removing the sportsbook's margin (vig). When Model % is meaningfully higher than Market %, our model sees potential value — that's the basis of a pick.",
      },
      {
        q: "What does \"Preliminary\" mean on picks?",
        a: "Preliminary picks are generated in the morning before confirmed lineups are released. They are based on projected starters and historical roster data. Once the official lineup is posted (usually 1–2 hours before first pitch), picks are recalculated using confirmed players and may change. Treat Preliminary picks as directional signals, not final recommendations.",
      },
      {
        q: "What does Confirmed vs Projected lineup mean?",
        a: "Confirmed means the official lineup has been submitted to the league and is locked in. Projected means we are using our best estimate of who will start based on historical patterns and available information — but it could change. Picks based on Confirmed lineups are more reliable because the model has the actual player data it needs.",
      },
      {
        q: "What is Kelly % and how much should I bet?",
        a: "Kelly % is a bankroll management formula that sizes a bet proportional to your edge. A higher Kelly % suggests the model sees a larger edge. We display a fractional Kelly recommendation (typically 1/4 or 1/2 Kelly) to reduce variance. That said, bankroll management is personal — no sizing formula eliminates risk, and you should never bet more than you are comfortable losing.",
      },
    ],
  },
  {
    category: "Platform mechanics",
    items: [
      {
        q: "Which sportsbooks does Credence target?",
        a: "Our models are calibrated and compared against Bovada lines. Bovada is the primary line we display and the benchmark we use for edge detection. If you use a different sportsbook, the displayed odds will differ and the calculated EV may not apply directly to your situation.",
      },
      {
        q: "Why does a pick say \"KC wins\" when I bet on KC and they lost?",
        a: "Picks are framed from the perspective of the predicted outcome — the team we think is more likely to win. If a pick says \"KC wins\" and KC is the away team, you would bet KC on the moneyline at the odds shown. The pick reflects our model's directional view, not how you place the bet in a sportsbook interface.",
      },
      {
        q: "What happens to a bet when a game is postponed?",
        a: "Postponed games are automatically voided in your bet log. The stake is returned and the game does not count toward your record. If the game is rescheduled and you want to track a new bet on the rescheduled game, you would log it separately.",
      },
      {
        q: "When are predictions updated each day?",
        a: "The model runs each morning and produces initial predictions based on probable starters and available data. Picks are then refreshed throughout the day as lineups are confirmed and odds move. The most reliable version of any pick is the one available closest to first pitch, once lineups are confirmed.",
      },
    ],
  },
  {
    category: "Trust & coverage",
    items: [
      {
        q: "How is the model built?",
        a: "We use a combination of gradient-boosted and probabilistic machine learning models trained on several seasons of MLB game data. Inputs include pitching matchups, team offense and defense metrics, ballpark factors, umpire tendencies, weather, and betting market signals. Models are evaluated out-of-sample and are only promoted to production when they demonstrate improvement over the previous version.",
      },
      {
        q: "What sport(s) does Credence cover?",
        a: "MLB baseball only, for the 2026 season. We are focused on doing one sport well before expanding. Additional sports are on the roadmap but have no committed timeline.",
      },
      {
        q: "How do I report a data issue?",
        a: (
          <>
            If you see incorrect odds, a wrong score, a missing game, or any data that looks wrong, email us at{" "}
            <a
              href="mailto:support@credencesports.com"
              className="text-[#10b981] hover:underline"
            >
              support@credencesports.com
            </a>
            . Include the game and date and we will investigate.
          </>
        ),
      },
    ],
  },
]

export default function FaqPage() {
  return (
    <div className="min-h-screen bg-background flex flex-col">
      <Nav />

      <main className="flex-1 mx-auto w-full max-w-3xl px-6 py-12">
        <div className="mb-10">
          <p className="text-xs uppercase tracking-widest text-muted-foreground mb-1">
            Credence Sports · A product of Penumbra Partners
          </p>
          <h1 className="text-3xl font-bold text-foreground">
            Frequently Asked Questions
          </h1>
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
            <div key={section.category}>
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
