"use client"

import { Suspense } from "react"
import Link from "next/link"
import { useParams, useSearchParams } from "next/navigation"
import { ChevronLeft } from "lucide-react"
import { Nav } from "@/components/nav"
import { AuthGuard } from "@/components/auth-guard"
import { useAuth } from "@/lib/auth-context"
import { BatterTbProjection } from "@/components/batter-tb-projection"

function BatterPropDetailInner() {
  const { batterId } = useParams<{ batterId: string }>()
  const searchParams = useSearchParams()
  const asOf = searchParams.get("as_of") // pin to the slate the /props list linked from
  const { email } = useAuth()
  const id = Number(batterId)

  return (
    <>
      <Nav authenticated activeLink="props" userEmail={email} />
      <main className="mx-auto max-w-3xl px-4 py-8">
        <Link
          href="/props"
          className="mb-4 inline-flex items-center gap-1 text-sm text-gray-500 transition-colors hover:text-gray-300"
        >
          <ChevronLeft className="h-4 w-4" />
          All props
        </Link>

        {Number.isFinite(id) ? (
          <BatterTbProjection batterId={id} asOf={asOf} />
        ) : (
          <p className="text-sm text-gray-500">Invalid batter.</p>
        )}

        <p className="mt-2 text-xs text-gray-600">
          Want this batter&apos;s full season stats and game log?{" "}
          <Link href={`/players/${id}`} className="text-gray-400 underline hover:text-gray-200">
            View player page
          </Link>
        </p>
      </main>
    </>
  )
}

export default function BatterPropDetailPage() {
  return (
    <AuthGuard>
      <Suspense fallback={null}>
        <BatterPropDetailInner />
      </Suspense>
    </AuthGuard>
  )
}
