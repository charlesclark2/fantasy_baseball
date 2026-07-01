"use client"

import Link from "next/link"
import { useParams } from "next/navigation"
import { ChevronLeft } from "lucide-react"
import { Nav } from "@/components/nav"
import { AuthGuard } from "@/components/auth-guard"
import { useAuth } from "@/lib/auth-context"
import { PitcherKProjection } from "@/components/pitcher-k-projection"

function PropDetailInner() {
  const { pitcherId } = useParams<{ pitcherId: string }>()
  const { email } = useAuth()
  const id = Number(pitcherId)

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
          <PitcherKProjection pitcherId={id} />
        ) : (
          <p className="text-sm text-gray-500">Invalid pitcher.</p>
        )}

        <p className="mt-2 text-xs text-gray-600">
          Want this pitcher&apos;s full season stats and game log?{" "}
          <Link href={`/players/${id}`} className="text-gray-400 underline hover:text-gray-200">
            View player page
          </Link>
        </p>
      </main>
    </>
  )
}

export default function PropDetailPage() {
  return (
    <AuthGuard>
      <PropDetailInner />
    </AuthGuard>
  )
}
