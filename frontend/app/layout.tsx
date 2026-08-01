import type { Metadata } from 'next'
import { Geist, Geist_Mono } from 'next/font/google'
import { Analytics } from '@vercel/analytics/next'
import { Providers } from '@/components/providers'
import { SiteFooter } from '@/components/site-footer'
import './globals.css'

const geist = Geist({ subsets: ['latin'] })
const geistMono = Geist_Mono({ subsets: ['latin'] })

export const metadata: Metadata = {
  title: 'Credence Sports',
  description: 'Bayesian sports analytics. Daily edge, quantified.',
  icons: {
    icon: '/brand/logo-icon.svg',
    shortcut: '/brand/logo-icon.svg',
    apple: '/brand/logo-icon.svg',
  },
  openGraph: {
    title: 'Credence Sports',
    description: 'Bayesian sports analytics. Daily edge, quantified.',
    images: ['/brand/logo-full.svg'],
  },
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    // suppressHydrationWarning applies to THIS element's attributes only (it is not recursive), so
    // it silences the one mismatch we can neither predict nor control: browser extensions —
    // password managers, Grammarly, dark-mode and translation tools — routinely stamp attributes
    // onto <html>/<body> before React hydrates. That surfaces as a "hydration failed" error with no
    // component attribution, which is noise that buries real mismatches in Sentry. Genuine
    // mismatches inside the tree still report normally.
    <html lang="en" className="dark" suppressHydrationWarning>
      <body
        className={`${geist.className} font-sans antialiased bg-background`}
      >
        <Providers>
          {children}
          <SiteFooter />
        </Providers>
        <Analytics />
      </body>
    </html>
  )
}
