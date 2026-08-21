"use client"

import { QueryClientProvider } from '@tanstack/react-query'
import { queryClient } from '@/lib/query-client'
import { AuthProvider } from '@/lib/auth-context'
import { DateProvider } from '@/lib/date-context'
import { TooltipProvider } from '@/components/ui/tooltip'
import { CookieBanner } from '@/components/cookie-banner'
import { Toaster } from '@/components/ui/toaster'
import { SubscriptionGate } from '@/components/subscription-gate'
import { FunnelTelemetry } from '@/components/funnel-telemetry'
import { PlatformAttributionProvider } from '@/components/fantasy/platform-attribution'

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider>
      <DateProvider>
        <QueryClientProvider client={queryClient}>
          <TooltipProvider>
            {/* G100-D0 — inside AuthProvider (it reads the session) and outside every page, so
                attribution + identity are registered before any page fires a funnel event. */}
            <FunnelTelemetry />
            <SubscriptionGate />
            {/* 🚩 Yahoo Cover Page — the credit must appear IN THE FOOTER of each page displaying
                their data, and `SiteFooter` is a SIBLING of the page inside this provider's own
                `children`. So it wraps BOTH: surfaces register what they are displaying, the
                footer slot draws it. Wrapping only the page would put the footer outside the
                provider and the credit would silently never render. */}
            <PlatformAttributionProvider>{children}</PlatformAttributionProvider>
            <CookieBanner />
            <Toaster />
          </TooltipProvider>
        </QueryClientProvider>
      </DateProvider>
    </AuthProvider>
  )
}
