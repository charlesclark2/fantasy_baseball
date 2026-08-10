import type { Metadata } from 'next'
import { Geist, Geist_Mono } from 'next/font/google'
import { Analytics } from '@vercel/analytics/next'
import { Providers } from '@/components/providers'
import { SiteFooter } from '@/components/site-footer'
import './globals.css'

const geist = Geist({ subsets: ['latin'] })
const geistMono = Geist_Mono({ subsets: ['latin'] })

// E9.46 — the site-wide description was "Bayesian sports analytics. Daily edge, quantified.",
// which is the claim `best_alpha = 0` forbids and was the SHARED default for every route that does
// not export its own metadata (i.e. the string a link preview showed when any of them was pasted
// into a chat). It is also single-vertical, from before the NFL fantasy product existed. The home
// route overrides both fields with `HERO.subhead`; this is the fallback for everything else.
// ⭐ E9.60 — FANTASY-FIRST (spec §2). E9.46 had already removed the "Daily edge, quantified" claim
// and the baseball-only framing; what it left was MLB-first ordering, which is the one place the
// site still stated a different product priority than the home page, About and the nav. This is the
// SEO/link-preview surface — the sentence a link shows when any route is pasted into a chat — so it
// is also the most widely distributed copy in the product.
const SITE_DESCRIPTION =
  'Transparent, model-driven sports analysis — NFL fantasy rankings and MLB betting intelligence, each published with the uncertainty around it.'

export const metadata: Metadata = {
  title: 'Credence Sports',
  description: SITE_DESCRIPTION,
  icons: {
    icon: '/brand/logo-icon.svg',
    shortcut: '/brand/logo-icon.svg',
    apple: '/brand/logo-icon.svg',
  },
  openGraph: {
    title: 'Credence Sports',
    description: SITE_DESCRIPTION,
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
