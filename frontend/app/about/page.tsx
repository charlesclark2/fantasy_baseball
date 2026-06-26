import Link from "next/link"
import { Nav } from "@/components/nav"

export const metadata = {
  title: "About Us — Credence Sports",
  description:
    "We forecast baseball the way the evidence supports — with the uncertainty shown, not hidden.",
}

export default function AboutPage() {
  return (
    <div className="min-h-screen bg-background flex flex-col">
      <Nav />

      <main className="flex-1 mx-auto w-full max-w-3xl px-6 py-16">

        {/* Eyebrow */}
        <p className="text-xs uppercase tracking-widest text-muted-foreground mb-10">
          Credence Sports
        </p>

        {/* POV Hero */}
        <div className="mb-16">
          <h1 className="text-4xl sm:text-5xl font-bold text-white leading-tight tracking-tight mb-5">
            An honest maybe beats a confident guess.
          </h1>
          <p className="text-base sm:text-lg text-gray-400 leading-relaxed max-w-xl">
            We forecast baseball the way the evidence supports — with the uncertainty shown,
            not hidden.
          </p>
        </div>

        {/* Origin moment — serif pull with left rule */}
        <div className="mb-16 border-l-2 border-[#10b981] pl-6">
          <p className="font-serif text-lg sm:text-xl text-gray-200 leading-relaxed italic">
            Baseball has more publicly available data than any other sport. The signal is
            there. What most models skip is the discipline to carry the uncertainty forward —
            to say honestly what the data can and can&apos;t tell you, instead of collapsing
            it into a number that implies more than it knows.
          </p>
          <p className="mt-4 font-serif text-base text-gray-400 leading-relaxed italic">
            Credence Sports started from that gap: not a lack of data, but a lack of honesty
            about its limits.
          </p>
        </div>

        {/* What we believe */}
        <div className="mb-16">
          <h2 className="text-xs uppercase tracking-widest text-muted-foreground mb-2">
            What we believe
          </h2>
          <div className="divide-y divide-[#262626]">
            <Principle index="01" title="Show the uncertainty.">
              Every estimate carries its range. A wide interval is information, not a flaw —
              it tells you exactly how much confidence the evidence warrants.
            </Principle>
            <Principle index="02" title="Close what fails.">
              When a model doesn&apos;t clear its own evaluation gates, we retire it — in
              public, with the post-mortem. A result that doesn&apos;t pass its own test
              isn&apos;t paused quietly; it&apos;s closed.
            </Principle>
            <Principle index="03" title="No false certainty.">
              Every pick carries its conviction score and credible interval — the uncertainty
              is on the label, not buried in footnotes. We don&apos;t sell win-rate streaks
              or dress any outcome up as a sure thing.
            </Principle>
            <Principle index="04" title="Show the work.">
              The estimate, the range, the signals behind it, the gates it had to clear —
              all visible. A model you can&apos;t evaluate is a model you&apos;re taking
              on faith.
            </Principle>
          </div>
        </div>

        {/* Who it's for */}
        <div className="mb-16">
          <h2 className="text-xs uppercase tracking-widest text-muted-foreground mb-4">
            Who it&apos;s for
          </h2>
          <p className="text-base sm:text-lg text-gray-300 leading-relaxed max-w-xl">
            Built for the person who spent time on Fangraphs wondering whether a
            pitcher&apos;s ERA was actually telling the truth — not the person who
            just wants a compelling story and a confident pick.
          </p>
        </div>

        {/* Footer / CTA */}
        <div className="border-t border-[#262626] pt-10">
          <p className="text-xs text-muted-foreground mb-6">
            A product of Penumbra Partners.
          </p>
          <div className="flex flex-wrap gap-3 mb-10">
            <Link
              href="/faq"
              className="inline-flex items-center rounded-md border border-[#262626] px-4 py-2 text-sm text-gray-300 hover:text-white hover:border-[#404040] transition-colors"
            >
              How a pick works →
            </Link>
            <a
              href="mailto:charlie@credencesports.com?subject=Beta%20Access%20Request"
              className="inline-flex items-center rounded-md bg-[#10b981] px-4 py-2 text-sm font-semibold text-[#0a0a0a] hover:bg-[#059669] transition-colors"
            >
              Request access
            </a>
          </div>
          <div className="flex flex-wrap gap-6 text-sm text-muted-foreground">
            <Link href="/blog" className="hover:text-foreground transition-colors">
              Blog
            </Link>
            <Link href="/faq" className="hover:text-foreground transition-colors">
              FAQ
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
        </div>

      </main>
    </div>
  )
}

function Principle({
  index,
  title,
  children,
}: {
  index: string
  title: string
  children: React.ReactNode
}) {
  return (
    <div className="py-5 flex gap-5 sm:gap-8 items-start">
      <span className="text-xs tabular-nums text-muted-foreground w-5 mt-0.5 shrink-0 select-none">
        {index}
      </span>
      <div>
        <p className="text-sm font-semibold text-white mb-1">{title}</p>
        <p className="text-sm text-gray-400 leading-relaxed">{children}</p>
      </div>
    </div>
  )
}
