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
    <html lang="en" className="dark">
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
