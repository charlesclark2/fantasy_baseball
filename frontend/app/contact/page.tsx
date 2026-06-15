import Link from "next/link"
import { Nav } from "@/components/nav"

export const metadata = {
  title: "Contact — Credence Sports",
}

export default function ContactPage() {
  return (
    <div className="min-h-screen bg-background flex flex-col">
      <Nav />

      <main className="flex-1 mx-auto w-full max-w-3xl px-6 py-12">
        <div className="mb-10">
          <p className="text-xs uppercase tracking-widest text-muted-foreground mb-1">
            Credence Sports · A product of Penumbra Partners
          </p>
          <h1 className="text-3xl font-bold text-foreground">Contact</h1>
        </div>

        <div className="space-y-10 text-sm text-gray-300 leading-relaxed">

          <div className="space-y-3">
            <h2 className="text-xs uppercase tracking-widest text-muted-foreground">
              Support
            </h2>
            <p>
              For questions about picks, platform issues, or data problems, email us at{" "}
              <a
                href="mailto:support@credencesports.com"
                className="text-[#10b981] hover:underline"
              >
                support@credencesports.com
              </a>
              . We typically respond within one business day.
            </p>
            <p>
              If you are reporting a specific data issue (wrong score, missing game, incorrect odds),
              include the game and date in your email so we can investigate quickly.
            </p>
          </div>

          <div className="space-y-3">
            <h2 className="text-xs uppercase tracking-widest text-muted-foreground">
              General inquiries
            </h2>
            <p>
              For partnership inquiries, press, or anything else, reach us at{" "}
              <a
                href="mailto:charlie@credencesports.com"
                className="text-[#10b981] hover:underline"
              >
                charlie@credencesports.com
              </a>
              .
            </p>
          </div>

          <div className="space-y-3">
            <h2 className="text-xs uppercase tracking-widest text-muted-foreground">
              Before you write
            </h2>
            <p>
              Our{" "}
              <Link href="/faq" className="text-[#10b981] hover:underline">
                FAQ
              </Link>{" "}
              covers the most common questions about how picks work, what EV means, which sportsbooks
              we model against, and how lineups affect predictions. It is worth a quick look first.
            </p>
          </div>

        </div>

        <div className="mt-12 pt-8 border-t border-[#262626] flex gap-6 text-sm text-muted-foreground">
          <Link href="/faq" className="hover:text-foreground transition-colors">
            FAQ
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
