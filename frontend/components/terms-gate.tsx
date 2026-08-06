"use client"

// E9.58b — the blocking acceptance gate.
//
// Signup records ToS acceptance on the /callback path, with one retry. This is what makes that
// a GUARANTEE rather than a best effort: any signed-in account the backend reports as having no
// `tos_accepted_at` is stopped here until the record actually lands. It also covers accounts
// created before E9.58 (admin invites that predate the set-password ToS step).
//
// Deliberate properties, each of which is the difference between a gate and an outage:
//   • fails OPEN when the backend does not report the field at all (deploy skew — see lib/terms.ts)
//   • fails OPEN when the profile read itself errors; a Dynamo blip must not lock everyone out
//   • CANNOT be dismissed — no close button, no overlay click-through, no Escape
//   • only clears once the write SUCCEEDS; an error keeps the modal up with a retry

import { useEffect, useState } from "react"
import Link from "next/link"
import { useQuery } from "@tanstack/react-query"
import { Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { useAuth } from "@/lib/auth-context"
import { acceptTerms, getTermsStatus } from "@/lib/terms"

export function TermsGate({ children }: { children: React.ReactNode }) {
  const { accessToken } = useAuth()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [justAccepted, setJustAccepted] = useState(false)

  const status = useQuery({
    queryKey: ["terms-status"],
    queryFn: () => getTermsStatus(accessToken),
    enabled: !!accessToken,
    staleTime: 5 * 60 * 1000,
    retry: 1,
  })

  // A signed-in account the backend positively reports as having NO acceptance record.
  // `status.isError` is excluded on purpose: an unreadable profile is not evidence of
  // non-acceptance, and treating it as such would lock every user out on a transient 503.
  const mustAccept =
    !!accessToken &&
    !justAccepted &&
    status.isSuccess &&
    status.data.known &&
    !status.data.accepted

  useEffect(() => {
    if (!mustAccept) return
    // Stop the page behind the modal from scrolling while it is up.
    const prev = document.body.style.overflow
    document.body.style.overflow = "hidden"
    return () => {
      document.body.style.overflow = prev
    }
  }, [mustAccept])

  async function handleAccept() {
    setError(null)
    setBusy(true)
    try {
      await acceptTerms(accessToken)
      // Only now is the record on file. Re-read rather than assuming, so the modal clears on
      // the backend's word rather than on ours.
      const fresh = await getTermsStatus(accessToken)
      if (fresh.known && !fresh.accepted) {
        throw new Error("Your acceptance was not saved. Please try again.")
      }
      setJustAccepted(true)
      status.refetch()
    } catch (err) {
      setError(
        err instanceof Error && err.message
          ? err.message
          : "We couldn't record your acceptance. Please try again.",
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      {children}
      {mustAccept && (
        <div
          className="fixed inset-0 z-[100] flex items-center justify-center bg-black/80 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="terms-gate-title"
        >
          <div className="w-full max-w-md rounded-xl border border-[#262626] bg-[#0f0f0f] p-6">
            <h2 id="terms-gate-title" className="text-lg font-semibold text-white">
              Before you continue
            </h2>
            <p className="mt-3 text-sm leading-relaxed text-gray-400">
              We don&apos;t have a record of your agreement to our terms. Please review and accept
              them to continue using Credence Sports.
            </p>

            <p className="mt-4 text-sm text-gray-300">
              <Link
                href="/terms"
                target="_blank"
                className="text-[#10b981] underline underline-offset-4 hover:text-[#059669]"
              >
                Terms of Service
              </Link>
              {" · "}
              <Link
                href="/privacy"
                target="_blank"
                className="text-[#10b981] underline underline-offset-4 hover:text-[#059669]"
              >
                Privacy Policy
              </Link>
            </p>

            {error && (
              <Alert variant="destructive" className="mt-4">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}

            <Button
              onClick={handleAccept}
              disabled={busy}
              className="mt-6 w-full bg-[#10b981] font-semibold text-[#0a0a0a] hover:bg-[#059669]"
            >
              {busy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
              I agree
            </Button>

            <p className="mt-3 text-center text-xs text-gray-500">
              Signing out without accepting is fine — you can accept next time you sign in.
            </p>
          </div>
        </div>
      )}
    </>
  )
}
