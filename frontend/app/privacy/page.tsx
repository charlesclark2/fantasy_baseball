import Link from "next/link"
import { Nav } from "@/components/nav"

export const metadata = {
  title: "Privacy Policy — Credence Sports",
}

export default function PrivacyPage() {
  return (
    <div className="min-h-screen bg-background flex flex-col">
      <Nav />

      <main className="flex-1 mx-auto w-full max-w-3xl px-6 py-12">
        <div className="mb-10">
          <p className="text-xs uppercase tracking-widest text-muted-foreground mb-1">Credence Sports · A product of Penumbra Partners</p>
          <h1 className="text-3xl font-bold text-foreground">Privacy Policy</h1>
          <p className="mt-2 text-sm text-muted-foreground">Effective Date: June 14, 2026 · Last Updated: June 14, 2026</p>
        </div>

        <div className="prose prose-invert prose-sm max-w-none space-y-8 text-gray-300 leading-relaxed">

          <Section title="1. Introduction">
            <p>Penumbra Partners ("we," "us," or "our") operates Credence Sports at credencesports.com. This Privacy Policy explains how we collect, use, store, and protect information about you when you use our Service.</p>
            <p>We take your privacy seriously. We do not sell your personal information. We do not use your data to serve you advertisements. We collect only what we need to provide the Service.</p>
          </Section>

          <Section title="2. Information We Collect">
            <h3 className="text-sm font-semibold text-gray-200 mt-4 mb-2">Information You Provide Directly</h3>
            <p><strong>Account information.</strong> When you create an account, we collect your email address and a password (stored as a secure hash — we never store your password in plain text). We use AWS Cognito to manage authentication.</p>
            <p><strong>Profile information.</strong> If you choose to provide it, we may collect your name and notification preferences including phone number for SMS alerts.</p>
            <p><strong>Bet log data.</strong> If you use the bet logging feature, we collect the bet records you enter including game, market, odds, stake, and outcome. This data is stored to provide you with performance tracking and is not shared with third parties.</p>
            <p><strong>Communications.</strong> If you contact us at <a href="mailto:support@credencesports.com" className="text-[#10b981] hover:underline">support@credencesports.com</a>, we retain those communications to respond to your inquiry and improve the Service.</p>
            <p><strong>Feedback.</strong> During the beta period, we may collect feedback you provide through the Service or directly to us.</p>

            <h3 className="text-sm font-semibold text-gray-200 mt-4 mb-2">Information Collected Automatically</h3>
            <p><strong>Usage data.</strong> We collect information about how you interact with the Service, including pages visited, features used, picks viewed, and time spent on the Service.</p>
            <p><strong>Device and browser information.</strong> We collect basic technical information including browser type, operating system, and device type to ensure the Service works correctly across different environments.</p>
            <p><strong>Log data.</strong> Our servers automatically record information including IP address, request timestamps, pages accessed, and error logs. This data is used for security monitoring and debugging.</p>
            <p><strong>Cookies and similar technologies.</strong> We use session cookies to maintain your logged-in state. We do not use tracking cookies for advertising purposes. We do not use third-party advertising cookies.</p>

            <h3 className="text-sm font-semibold text-gray-200 mt-4 mb-2">Information We Do Not Collect</h3>
            <p>We do not collect:</p>
            <ul>
              <li>Payment card numbers or banking information (payment processing, if introduced, will be handled entirely by a third-party processor such as Stripe — we never see your card details)</li>
              <li>Government-issued identification numbers</li>
              <li>Precise geolocation data</li>
              <li>Biometric data</li>
              <li>Information about your actual betting accounts, balances, or activity on sportsbooks</li>
            </ul>
          </Section>

          <Section title="3. How We Use Your Information">
            <p>We use the information we collect for the following purposes:</p>
            <p><strong>Providing the Service.</strong> To authenticate your identity, display picks and analytics tailored to your account, process your bet log entries, and deliver notifications you have requested.</p>
            <p><strong>Improving the Service.</strong> To understand how users interact with the product, identify bugs and performance issues, and prioritize new features during the beta period.</p>
            <p><strong>Communications.</strong> To send you notifications about new picks if you have opted in, to respond to your support requests, and to send important account-related communications such as password reset emails.</p>
            <p><strong>Safety and security.</strong> To detect, investigate, and prevent fraudulent or unauthorized activity, abuse of the Service, or violations of our Terms of Service.</p>
            <p><strong>Legal compliance.</strong> To comply with applicable laws and regulations and to respond to lawful requests from government authorities.</p>
            <p><strong>Analytics.</strong> To measure aggregate usage patterns and model performance. All analytics are performed on aggregated, anonymized data where possible.</p>
            <p>We do not use your information for targeted advertising, selling to third parties, building profiles for resale, or any purpose not described in this Privacy Policy without your explicit consent.</p>
          </Section>

          <Section title="4. How We Share Your Information">
            <p className="font-semibold text-gray-200">We do not sell your personal information.</p>
            <p>We share your information only in the following limited circumstances:</p>
            <p><strong>Service providers.</strong> We share information with third-party vendors who help us operate the Service, including:</p>
            <ul>
              <li>Amazon Web Services (AWS) — cloud infrastructure, authentication (Cognito), storage (S3), and compute (Lambda)</li>
              <li>Snowflake — data warehouse for analytics pipeline (model data only — no personal information)</li>
            </ul>
            <p>These providers are contractually required to use your information only to provide services to us and in accordance with this Privacy Policy.</p>
            <p><strong>Legal requirements.</strong> We may disclose your information if required to do so by law or in response to a valid legal request such as a subpoena, court order, or government demand. We will attempt to notify you of such requests unless prohibited by law or court order.</p>
            <p><strong>Business transfers.</strong> If Penumbra Partners is acquired by or merges with another company, your information may be transferred as part of that transaction. We will notify you via email or prominent notice on the Service before your information becomes subject to a different privacy policy.</p>
            <p><strong>With your consent.</strong> We may share your information for any other purpose with your explicit consent.</p>
            <p><strong>Aggregate and anonymized data.</strong> We may share aggregate, anonymized statistics about Service usage with no information that could identify you individually.</p>
          </Section>

          <Section title="5. Data Retention">
            <p>We retain your personal information for as long as your account is active or as needed to provide the Service. Specifically:</p>
            <ul>
              <li>Account information is retained for the duration of your account and deleted within 90 days of account closure upon request</li>
              <li>Bet log data is retained for the duration of your account — this is your data and you can export or delete it</li>
              <li>Usage logs are retained for up to 12 months for security and debugging purposes</li>
              <li>Email communications are retained for up to 3 years</li>
            </ul>
            <p>You may request deletion of your account and associated data at any time by contacting us at <a href="mailto:support@credencesports.com" className="text-[#10b981] hover:underline">support@credencesports.com</a>. We will process deletion requests within 30 days.</p>
          </Section>

          <Section title="6. Data Security">
            <p>We implement industry-standard security measures to protect your information, including:</p>
            <ul>
              <li>All data transmitted between your browser and our servers is encrypted using TLS (HTTPS)</li>
              <li>Passwords are never stored in plain text — authentication is managed by AWS Cognito using secure hashing</li>
              <li>Access to production systems is restricted to authorized personnel only</li>
              <li>AWS infrastructure benefits from AWS's comprehensive security certifications and controls</li>
            </ul>
            <p>However, no method of transmission over the internet or method of electronic storage is 100% secure. While we strive to protect your personal information, we cannot guarantee absolute security. In the event of a data breach that affects your personal information, we will notify you as required by applicable law.</p>
          </Section>

          <Section title="7. Your Rights and Choices">
            <p>Depending on your jurisdiction, you may have certain rights regarding your personal information:</p>
            <p><strong>Access.</strong> You may request a copy of the personal information we hold about you.</p>
            <p><strong>Correction.</strong> You may request that we correct inaccurate personal information about you.</p>
            <p><strong>Deletion.</strong> You may request that we delete your personal information, subject to certain exceptions (such as information we are required to retain by law).</p>
            <p><strong>Portability.</strong> You may request that we provide your personal information in a portable format.</p>
            <p><strong>Opt-out of communications.</strong> You may opt out of non-essential communications at any time through your account settings or by contacting us.</p>
            <p><strong>Notification preferences.</strong> You can manage your push notification and email alert preferences in the Settings section of the Service at any time.</p>
            <p>To exercise any of these rights, contact us at <a href="mailto:support@credencesports.com" className="text-[#10b981] hover:underline">support@credencesports.com</a>. We will respond to your request within 30 days.</p>
          </Section>

          <Section title="8. Cookies">
            <p><strong>Essential cookies.</strong> Required for the Service to function. These include session cookies that keep you logged in. You cannot opt out of essential cookies without discontinuing use of the Service.</p>
            <p><strong>Analytics cookies.</strong> We may use basic analytics to understand usage patterns. These are not advertising cookies and do not track you across other websites.</p>
            <p>We do not use third-party advertising cookies. We do not participate in any advertising networks or retargeting programs.</p>
            <p>You can control cookies through your browser settings. Disabling cookies may affect your ability to use certain features of the Service.</p>
          </Section>

          <Section title="9. Third-Party Links">
            <p>The Service may contain links to third-party websites or services, including sportsbooks and betting platforms referenced in our content. This Privacy Policy does not apply to those third-party services. We encourage you to review the privacy policies of any third-party services you access through the Service.</p>
          </Section>

          <Section title="10. Children's Privacy">
            <p>The Service is not directed to individuals under the age of 18. We do not knowingly collect personal information from anyone under 18. If we become aware that we have collected personal information from a person under 18, we will take steps to delete that information promptly.</p>
            <p>If you believe we may have inadvertently collected information from a minor, please contact us at <a href="mailto:support@credencesports.com" className="text-[#10b981] hover:underline">support@credencesports.com</a>.</p>
          </Section>

          <Section title="11. California Privacy Rights">
            <p>If you are a California resident, you have additional rights under the California Consumer Privacy Act (CCPA) and California Privacy Rights Act (CPRA), including:</p>
            <ul>
              <li>The right to know what personal information we collect</li>
              <li>The right to delete your personal information</li>
              <li>The right to opt out of the sale of your personal information (we do not sell personal information)</li>
              <li>The right to non-discrimination for exercising your privacy rights</li>
            </ul>
            <p>To exercise your California privacy rights, contact us at <a href="mailto:support@credencesports.com" className="text-[#10b981] hover:underline">support@credencesports.com</a>.</p>
          </Section>

          <Section title="12. Changes to This Privacy Policy">
            <p>We may update this Privacy Policy from time to time. We will notify you of material changes by posting the updated policy with a new effective date and, for significant changes, by sending an email to the address associated with your account.</p>
            <p>Your continued use of the Service after the effective date of any changes constitutes your acceptance of the updated Privacy Policy.</p>
          </Section>

          <Section title="13. Contact">
            <p>For questions, concerns, or requests regarding this Privacy Policy or our data practices, contact us at:</p>
            <address className="not-italic mt-2 text-gray-400">
              Penumbra Partners / Credence Sports<br />
              <a href="mailto:support@credencesports.com" className="text-[#10b981] hover:underline">support@credencesports.com</a><br />
              <a href="https://credencesports.com" className="text-[#10b981] hover:underline">credencesports.com</a>
            </address>
          </Section>

        </div>

        <div className="mt-12 pt-8 border-t border-[#262626] flex gap-6 text-sm text-muted-foreground">
          <Link href="/terms" className="hover:text-foreground transition-colors">Terms of Service</Link>
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
