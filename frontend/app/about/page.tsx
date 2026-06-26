import Link from "next/link"
import { Nav } from "@/components/nav"

export const metadata = {
  title: "About Us — Credence Sports",
  description:
    "Credence Sports is a baseball analytics platform built on honest accounting of uncertainty. We show our work — including the unflattering parts.",
}

export default function AboutPage() {
  return (
    <div className="min-h-screen bg-background flex flex-col">
      <Nav />

      <main className="flex-1 mx-auto w-full max-w-3xl px-6 py-12">
        <div className="mb-10">
          <p className="text-xs uppercase tracking-widest text-muted-foreground mb-1">
            Credence Sports · A product of Penumbra Partners
          </p>
          <h1 className="text-3xl font-bold text-foreground">About Us</h1>
          <p className="mt-3 text-base text-gray-400 leading-relaxed max-w-2xl">
            We build baseball analytics tools on a simple premise: good predictions require
            honest accounting of uncertainty.
          </p>
        </div>

        <div className="space-y-10 text-gray-300 leading-relaxed">

          <Section title="We operate in the penumbra.">
            <p>
              Penumbra Partners is the company behind Credence Sports. The name is deliberate.
              The penumbra is the space between certainty and ignorance — where careful,
              evidence-based reasoning can make a difference precisely because the answer isn&apos;t
              obvious.
            </p>
            <p>
              We don&apos;t operate in the obvious. We operate in the gray zone where a model&apos;s
              estimate diverges from the market&apos;s, where uncertainty deserves to be shown rather
              than hidden, and where intellectual honesty about what we don&apos;t know is as important
              as the predictions themselves.
            </p>
          </Section>

          <Section title="Where this came from.">
            <p>
              Credence Sports started with baseball, a love of data, and a long-running frustration
              that the gap between what you can know about a game and what you can rigorously act
              on is too wide.
            </p>
            <p>
              Baseball is the sport that invented sabermetrics. It has more publicly available
              data than any other sport — pitch-level Statcast data, spin rates, exit velocity,
              expected batting average on every ball in play. All of it out there, free, updated
              in real time. The signal is there. The gap is the rigorous framework to turn it into
              decisions.
            </p>
            <p>
              Edge isn&apos;t knowing that a pitcher is good. Edge is knowing that the pitcher is
              better than the market currently believes, by a specific quantifiable amount, with
              an honest accounting of how uncertain you are about that estimate. That&apos;s a
              completely different problem — and it&apos;s the problem Credence Sports is built to solve.
            </p>
          </Section>

          <Section title="Why Bayesian statistics.">
            <p>
              We use Bayesian methods because they&apos;re the right tool for this problem.
              Bayesian reasoning treats probability as a measure of rational confidence — exactly
              what you need when making decisions about single events that will happen once and
              never be repeated under identical conditions.
            </p>
            <p>
              When you see a pick on Credence Sports, you don&apos;t just see a probability.
              You see an 80% credible interval — the range within which the true probability
              is likely to fall. That range is the honest answer. A narrow interval means the
              signals align and the estimate is tight. A wide interval means there&apos;s genuine
              uncertainty and you should weigh that accordingly.
            </p>
            <p>
              Bayesian reasoning also handles small samples gracefully — pulling extreme
              early-season observations toward realistic baselines, weighted by how much
              evidence has actually accumulated. And when data is missing, the uncertainty
              propagates into the output rather than being silently ignored. The signal
              completeness score on every pick tells you exactly how much information was
              available when the model generated its estimate.
            </p>
          </Section>

          <Section title="Transparency as method, not marketing.">
            <p>
              Most analytics platforms give you a number. We give you the model&apos;s full output:
              the probability estimate, the uncertainty range, the signal breakdown, and the
              gate criteria. We do this because a model that hides its uncertainty is a model
              you can&apos;t evaluate. And a model you can&apos;t evaluate is a model you&apos;re
              taking on faith.
            </p>
            <p>
              We&apos;re not asking you to take anything on faith. We&apos;re showing you the math.
            </p>
            <p>
              That requires a particular kind of intellectual honesty: the willingness to say,
              in public, that a model didn&apos;t pass its own evaluation criteria. When a modeling
              path doesn&apos;t clear its gates, we close it rather than deploy it quietly. When a
              pick has positive expected value but a wide credible interval, it gets a LOW
              conviction score rather than being dressed up to look more certain than it is.
              The uncertainty is visible, not buried.
            </p>
          </Section>

          <Section title="What we don't claim.">
            <p>
              We don&apos;t publish win-rate streaks or promise market edges. Our models are in
              active evaluation — a pick reaches the dashboard only when it clears simultaneous
              criteria: edge above minimum threshold, full credible interval above the market
              line, signal completeness, and conviction gate.
            </p>
            <p>
              When models don&apos;t meet those standards, we say so. When a feature turns out to
              be data leakage, we publish the post-mortem. The EV Tracker shows every market
              and every edge calculation — we don&apos;t gate the data, only what we&apos;re willing
              to call a qualified pick. The honesty is the product.
            </p>
          </Section>

          <Section title={'Why “Credence.”'}>
            <p>
              In Bayesian epistemology, a credence is a degree of belief — a probability
              assigned to a proposition based on available evidence. When the model processes
              tonight&apos;s pitching matchup, it&apos;s computing credences. When it updates on lineup
              confirmation, it&apos;s updating credences. The mathematical framework underlying
              every pick on this platform is literally a system for computing and revising
              credences.
            </p>
            <p>
              But credence also means something in ordinary language: credibility,
              trustworthiness, the quality of deserving to be believed. As in
              &ldquo;lend credence&rdquo; to an argument.
            </p>
            <p>
              We&apos;re trying to be both things simultaneously. A platform that has earned
              the right to be believed because it shows its work — including the
              unflattering parts. That&apos;s the whole project.
            </p>
          </Section>

          <Section title="Who this is for.">
            <p>
              If you want a simple lock of the day with a compelling narrative about why a
              team is due, this probably isn&apos;t the right platform for you.
            </p>
            <p>
              If you&apos;re the kind of person who spent time on Fangraphs trying to understand
              whether a pitcher&apos;s ERA was telling the truth — who found the Moneyball story
              interesting not because it was a movie but because it was proof of concept for
              evidence-based decision-making in a domain dominated by intuition — this is
              built for you.
            </p>
            <p>
              It&apos;s also built for people who are curious about Bayesian statistics and want
              to see what it actually looks like when you apply it seriously to a real domain
              with real stakes.
            </p>
          </Section>

        </div>

        {/* CTA */}
        <div className="mt-12 rounded-lg border border-[#262626] bg-[#0f0f0f] px-6 py-8">
          <p className="text-xs uppercase tracking-widest text-muted-foreground mb-2">
            Credence Sports is in beta
          </p>
          <p className="text-sm text-gray-400 leading-relaxed mb-5">
            We started with baseball because it&apos;s the sport with the richest publicly
            available data and the deepest analytical tradition. The same framework
            extends to football and basketball — that expansion is on the roadmap.
          </p>
          <div className="flex flex-wrap gap-3">
            <Link
              href="/blog"
              className="inline-flex items-center gap-1.5 rounded-md border border-[#262626] px-4 py-2 text-sm text-gray-300 hover:text-white hover:border-[#404040] transition-colors"
            >
              Read the blog →
            </Link>
            <a
              href="mailto:charlie@credencesports.com?subject=Beta%20Access%20Request"
              className="inline-flex items-center gap-1.5 rounded-md bg-[#10b981] px-4 py-2 text-sm font-semibold text-[#0a0a0a] hover:bg-[#059669] transition-colors"
            >
              Request access
            </a>
          </div>
        </div>

        <div className="mt-12 pt-8 border-t border-[#262626] flex flex-wrap gap-6 text-sm text-muted-foreground">
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
      </main>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h2 className="text-base font-semibold text-gray-100 mb-3">{title}</h2>
      <div className="space-y-3 text-sm">{children}</div>
    </section>
  )
}
