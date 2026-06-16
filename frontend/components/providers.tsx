"use client"

import { QueryClientProvider } from '@tanstack/react-query'
import { queryClient } from '@/lib/query-client'
import { AuthProvider } from '@/lib/auth-context'
import { DateProvider } from '@/lib/date-context'
import { TooltipProvider } from '@/components/ui/tooltip'
import { CookieBanner } from '@/components/cookie-banner'
import { Toaster } from '@/components/ui/toaster'

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider>
      <DateProvider>
        <QueryClientProvider client={queryClient}>
          <TooltipProvider>
            {children}
            <CookieBanner />
            <Toaster />
          </TooltipProvider>
        </QueryClientProvider>
      </DateProvider>
    </AuthProvider>
  )
}
