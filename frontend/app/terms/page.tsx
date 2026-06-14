import Link from "next/link"
import { Nav } from "@/components/nav"

export const metadata = {
  title: "Terms of Service — Credence Sports",
}

export default function TermsPage() {
  return (
    <div className="min-h-screen bg-background flex flex-col">
      <Nav />

      <main className="flex-1 mx-auto w-full max-w-3xl px-6 py-12">
        <div className="mb-10">
          <p className="text-xs uppercase tracking-widest text-muted-foreground mb-1">Credence Sports · A product of Penumbra Partners</p>
          <h1 className="text-3xl font-bold text-foreground">Terms of Service</h1>
          <p className="mt-2 text-sm text-muted-foreground">Effective Date: June 14, 2026 · Last Updated: June 14, 2026</p>
        </div>

        <div className="prose prose-invert prose-sm max-w-none space-y-8 text-gray-300 leading-relaxed">

          <Section title="1. Agreement to Terms">
            <p>By accessing or using Credence Sports ("the Service," "we," "us," or "our"), operated by Penumbra Partners, you agree to be bound by these Terms of Service ("Terms"). If you do not agree to these Terms, do not use the Service.</p>
            <p>These Terms apply to all users of the Service, including beta testers, subscribers, and administrators. Your continued use of the Service following any changes to these Terms constitutes acceptance of those changes.</p>
          </Section>

          <Section title="2. Description of Service">
            <p>Credence Sports is a quantitative sports analytics platform that produces probability estimates and statistical analysis for sports betting markets. The Service provides:</p>
            <ul>
              <li>Bayesian probability estimates for sports game outcomes</li>
              <li>Expected value calculations and Kelly-sized stake recommendations</li>
              <li>Historical performance tracking and model analytics</li>
              <li>Bet logging and outcome tracking tools</li>
              <li>Administrative and pipeline monitoring tools (for authorized administrators only)</li>
            </ul>
            <p>The Service is an informational and analytical tool only. Credence Sports does not facilitate, process, or execute any wagers. We do not accept money for betting purposes. We do not operate as a sportsbook, sports betting operator, or gambling service.</p>
          </Section>

          <Section title="3. Eligibility">
            <p>You must meet all of the following criteria to use the Service:</p>
            <ul>
              <li>You must be at least 18 years of age, or the legal age of majority in your jurisdiction, whichever is greater</li>
              <li>You must be located in a jurisdiction where accessing sports analytics and betting-related informational content is legal</li>
              <li>You must not be prohibited by any applicable law, regulation, or court order from accessing gambling-adjacent informational services</li>
              <li>You must have the legal capacity to enter into a binding agreement</li>
            </ul>
            <p>By using the Service, you represent and warrant that you meet all eligibility requirements. If you do not meet these requirements, you must discontinue use of the Service immediately.</p>
            <p><strong>Geographic Restrictions.</strong> It is your sole responsibility to determine whether accessing the Service is legal in your jurisdiction. Penumbra Partners makes no representation that the Service is appropriate or available for use in any particular location.</p>
          </Section>

          <Section title="4. Beta Access">
            <p>During the beta period, access to the Service is by invitation only. Beta testers receive full access to the Service at no charge in exchange for providing feedback to help improve the product.</p>
            <p>By participating in the beta program, you agree to:</p>
            <ul>
              <li>Provide honest and constructive feedback when requested</li>
              <li>Not share your login credentials with any other person</li>
              <li>Not publicly disclose proprietary model outputs, pick data, or performance statistics without prior written consent from Penumbra Partners</li>
              <li>Accept that the Service may be unstable, incomplete, or subject to significant changes during the beta period</li>
              <li>Accept that beta access may be revoked at any time at our sole discretion</li>
            </ul>
            <p>Beta testers are not employees, contractors, or agents of Penumbra Partners. Participation in the beta program creates no employment, partnership, or agency relationship.</p>
          </Section>

          <Section title="5. Accounts and Security">
            <p><strong>Account Creation.</strong> To access the Service, you must create an account through our authentication system. You agree to provide accurate, current, and complete information during registration.</p>
            <p><strong>Account Security.</strong> You are responsible for maintaining the confidentiality of your account credentials. You agree to notify us immediately at <a href="mailto:hello@credencesports.com" className="text-[#10b981] hover:underline">hello@credencesports.com</a> if you become aware of any unauthorized access to your account.</p>
            <p><strong>Account Responsibility.</strong> You are responsible for all activity that occurs under your account, whether or not you authorized it. Penumbra Partners is not liable for any loss or damage arising from your failure to maintain account security.</p>
            <p><strong>Account Termination.</strong> We reserve the right to suspend or terminate your account at any time for any reason, including but not limited to violation of these Terms, suspicious activity, or at our sole discretion during the beta period.</p>
          </Section>

          <Section title="6. Acceptable Use">
            <p>You agree to use the Service only for lawful purposes and in accordance with these Terms. You agree not to:</p>
            <ul>
              <li>Use the Service in any way that violates any applicable law or regulation</li>
              <li>Use the Service to facilitate any illegal activity, including illegal gambling</li>
              <li>Attempt to circumvent, disable, or interfere with security features of the Service</li>
              <li>Access or attempt to access any part of the Service you are not authorized to access</li>
              <li>Use automated scripts, bots, scrapers, or other automated means to access or collect data from the Service without prior written consent</li>
              <li>Reverse engineer, decompile, or disassemble any part of the Service</li>
              <li>Transmit any material that is unlawful, harmful, defamatory, obscene, or otherwise objectionable</li>
              <li>Impersonate any person or entity or misrepresent your affiliation with any person or entity</li>
              <li>Interfere with or disrupt the integrity or performance of the Service or its underlying infrastructure</li>
              <li>Share, resell, sublicense, or redistribute access to the Service or any data produced by the Service without prior written consent</li>
            </ul>
          </Section>

          <Section title="7. Intellectual Property">
            <p><strong>Our Content.</strong> The Service and all of its content, features, and functionality — including but not limited to the model architecture, probability estimates, signal calculations, software code, design, text, graphics, and logos — are owned by Penumbra Partners and are protected by applicable intellectual property laws.</p>
            <p><strong>Limited License.</strong> We grant you a limited, non-exclusive, non-transferable, revocable license to access and use the Service for your personal, non-commercial use in accordance with these Terms. This license does not include the right to:</p>
            <ul>
              <li>Reproduce, distribute, or publicly display any content from the Service</li>
              <li>Create derivative works based on the Service or its content</li>
              <li>Use the Service for any commercial purpose without prior written consent</li>
              <li>Use any data mining, scraping, or data gathering methods on the Service</li>
            </ul>
            <p><strong>Your Content.</strong> You retain ownership of any content you submit to the Service, including bet log entries and notes. By submitting content to the Service, you grant Penumbra Partners a non-exclusive, royalty-free license to use, store, and display that content for the purpose of providing the Service.</p>
            <p><strong>Feedback.</strong> Any feedback, suggestions, or ideas you provide regarding the Service may be used by Penumbra Partners without any obligation to compensate you or maintain confidentiality.</p>
          </Section>

          <Section title="8. Disclaimer of Warranties">
            <p className="uppercase font-semibold text-gray-200">The Service is provided "as is" and "as available" without warranties of any kind, either express or implied.</p>
            <p>To the fullest extent permitted by applicable law, Penumbra Partners expressly disclaims all warranties, including but not limited to:</p>
            <ul>
              <li>Warranties of merchantability, fitness for a particular purpose, and non-infringement</li>
              <li>Warranties that the Service will be uninterrupted, error-free, or free of viruses or other harmful components</li>
              <li>Warranties regarding the accuracy, reliability, completeness, or timeliness of any content, data, or predictions produced by the Service</li>
              <li>Warranties that any particular outcome predicted by the model will occur</li>
            </ul>
            <p>The model's probability estimates are statistical outputs based on available data. They are not guarantees of any outcome. Sports events are inherently unpredictable. Past model performance does not guarantee future results.</p>
          </Section>

          <Section title="9. Limitation of Liability">
            <p className="uppercase font-semibold text-gray-200">To the fullest extent permitted by applicable law, in no event will Penumbra Partners, its officers, directors, employees, agents, or affiliates be liable for any:</p>
            <ul className="uppercase">
              <li>Indirect, incidental, special, consequential, or punitive damages</li>
              <li>Loss of profits, revenue, data, business, or goodwill</li>
              <li>Damages arising from your use of or inability to use the Service</li>
              <li>Damages arising from any wagers placed based on information from the Service</li>
              <li>Damages arising from unauthorized access to or alteration of your account or data</li>
            </ul>
            <p className="uppercase font-semibold text-gray-200">In no event will our total liability to you for all claims arising from or related to these Terms or the Service exceed the greater of (a) the amount you paid to Penumbra Partners in the twelve months preceding the claim or (b) one hundred dollars ($100).</p>
            <p>Some jurisdictions do not allow the exclusion or limitation of certain damages. In such jurisdictions, our liability will be limited to the fullest extent permitted by applicable law.</p>
          </Section>

          <Section title="10. Indemnification">
            <p>You agree to indemnify, defend, and hold harmless Penumbra Partners and its officers, directors, employees, agents, and affiliates from and against any claims, liabilities, damages, judgments, awards, losses, costs, expenses, or fees (including reasonable attorneys' fees) arising out of or relating to:</p>
            <ul>
              <li>Your violation of these Terms</li>
              <li>Your use of the Service</li>
              <li>Any wagers or financial decisions you make based on information from the Service</li>
              <li>Your violation of any third-party rights</li>
              <li>Your violation of any applicable law or regulation</li>
            </ul>
          </Section>

          <Section title="11. Informational Nature of the Service">
            <p className="font-semibold text-gray-200 border border-[#10b981]/30 bg-[#10b981]/5 rounded p-4">This is critically important. Please read carefully.</p>
            <p>All picks, probability estimates, expected value calculations, Kelly stake recommendations, and other outputs of the Service are informational only. They are the outputs of a statistical model and represent the model's assessment of available data at the time of generation.</p>
            <ul>
              <li>Credence Sports is not a licensed financial advisor</li>
              <li>Credence Sports is not a licensed sports betting operator</li>
              <li>Credence Sports does not provide personalized financial advice</li>
              <li>No output of the Service should be construed as a recommendation to place any specific wager</li>
              <li>You are solely and entirely responsible for any and all wagers you choose to place</li>
              <li>You are solely and entirely responsible for determining the legality of sports betting in your jurisdiction</li>
              <li>You are solely and entirely responsible for any financial consequences of your betting decisions</li>
            </ul>
            <p className="border-l-2 border-[#10b981]/50 pl-4">Gambling involves significant financial risk. Never wager more than you can afford to lose. If you or someone you know has a gambling problem, please seek help from the National Council on Problem Gambling at <strong>1-800-522-4700</strong> or <a href="https://ncpgambling.org" target="_blank" rel="noopener noreferrer" className="text-[#10b981] hover:underline">ncpgambling.org</a>.</p>
          </Section>

          <Section title="12. Third-Party Services">
            <p>The Service may contain links to or integrations with third-party services, including but not limited to payment processors, data providers, and cloud infrastructure providers. These third-party services are governed by their own terms of service and privacy policies.</p>
            <p>Penumbra Partners is not responsible for the content, accuracy, or practices of any third-party service. The inclusion of any link or integration does not constitute endorsement of the third-party service.</p>
          </Section>

          <Section title="13. Modifications to the Service">
            <p>Penumbra Partners reserves the right to modify, suspend, or discontinue the Service, or any part of it, at any time with or without notice. We will not be liable to you or any third party for any modification, suspension, or discontinuation of the Service.</p>
            <p>During the beta period in particular, the Service may change significantly and without advance notice as we continue development.</p>
          </Section>

          <Section title="14. Modifications to These Terms">
            <p>We reserve the right to modify these Terms at any time. We will notify you of material changes by posting the updated Terms to the Service with a new effective date, or by sending an email to the address associated with your account.</p>
            <p>Your continued use of the Service after the effective date of any changes constitutes your acceptance of the updated Terms. If you do not agree to the updated Terms, you must stop using the Service.</p>
          </Section>

          <Section title="15. Governing Law and Dispute Resolution">
            <p>These Terms are governed by and construed in accordance with the laws of the State of Wisconsin, without regard to its conflict of law provisions.</p>
            <p>Any dispute arising from or relating to these Terms or the Service will be resolved through binding arbitration administered by the American Arbitration Association under its Consumer Arbitration Rules, rather than in court, except that either party may seek injunctive or other equitable relief in any court of competent jurisdiction for claims involving intellectual property rights or unauthorized use of the Service.</p>
            <p><strong>Class Action Waiver.</strong> You agree that any arbitration or proceeding will be conducted on an individual basis and not as a class, consolidated, or representative action.</p>
          </Section>

          <Section title="16. Severability">
            <p>If any provision of these Terms is held to be invalid, illegal, or unenforceable, the remaining provisions will continue in full force and effect.</p>
          </Section>

          <Section title="17. Entire Agreement">
            <p>These Terms, together with our <Link href="/privacy" className="text-[#10b981] hover:underline">Privacy Policy</Link>, constitute the entire agreement between you and Penumbra Partners regarding the Service and supersede all prior agreements and understandings.</p>
          </Section>

          <Section title="18. Contact">
            <p>For questions about these Terms, contact us at:</p>
            <address className="not-italic mt-2 text-gray-400">
              Penumbra Partners / Credence Sports<br />
              <a href="mailto:hello@credencesports.com" className="text-[#10b981] hover:underline">hello@credencesports.com</a><br />
              <a href="https://credencesports.com" className="text-[#10b981] hover:underline">credencesports.com</a>
            </address>
          </Section>

        </div>

        <div className="mt-12 pt-8 border-t border-[#262626] flex gap-6 text-sm text-muted-foreground">
          <Link href="/privacy" className="hover:text-foreground transition-colors">Privacy Policy</Link>
          <Link href="/login" className="hover:text-foreground transition-colors">Sign In</Link>
        </div>
      </main>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h2 className="text-base font-semibold text-gray-100 mb-3">{title}</h2>
      <div className="space-y-3">{children}</div>
    </section>
  )
}
