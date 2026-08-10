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
            {children}
            <CookieBanner />
            <Toaster />
          </TooltipProvider>
        </QueryClientProvider>
      </DateProvider>
    </AuthProvider>
  )
}
