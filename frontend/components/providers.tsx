"use client"

import { QueryClientProvider } from '@tanstack/react-query'
import { queryClient } from '@/lib/query-client'
import { AuthProvider } from '@/lib/auth-context'
import { DateProvider } from '@/lib/date-context'
import { TooltipProvider } from '@/components/ui/tooltip'

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider>
      <DateProvider>
        <QueryClientProvider client={queryClient}>
          <TooltipProvider>{children}</TooltipProvider>
        </QueryClientProvider>
      </DateProvider>
    </AuthProvider>
  )
}
