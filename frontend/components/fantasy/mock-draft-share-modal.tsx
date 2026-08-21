"use client"

// The post-draft SHARE modal (NF-DS). Pops once when a mock draft completes; reopenable from the
// "Share your grade" button GradeCard renders beside "Draft a new room".
//
// ⭐ REUSE, NOT A FORK (E9.61). This never recomputes a rank, a position delta or a steal — it reads
// `buildShareSummary(grade, leagueLabel)`, which itself only reads fields off the SAME `DraftGrade`
// `GradeCard` renders. The branded image shown here IS the artifact a viewer gets (same route, same
// query string) — there is no second "preview" rendering to drift from the real one.
//
// PM decision, recorded: the share ARTIFACT (the image + its public landing page) is public and
// branded even though this modal only ever appears inside the paid mock-draft tool (FantasyGuard).

import { useEffect, useState } from "react"
import { Copy, Download, Share2 } from "lucide-react"
import posthog from "posthog-js"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { GRADE_CIRCULARITY_NOTE, buildShareSummary, ordinal, type DraftGrade } from "@/lib/mock-draft"
import { shareImagePath, sharePageUrl } from "@/lib/mock-draft-share"

export function MockDraftShareModal({
  open,
  onOpenChange,
  grade,
  leagueLabel,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  grade: DraftGrade | null
  leagueLabel: string
}) {
  const [copied, setCopied] = useState(false)
  const summary = grade ? buildShareSummary(grade, leagueLabel) : null

  const track = (event: string) =>
    summary &&
    posthog.capture(event, {
      league_format: leagueLabel,
      n_teams: summary.nTeams,
      rank: summary.rank,
    })

  // ⚠️ NOT `<Dialog onOpenChange>` — Radix only invokes that callback for a DISMISS it initiates
  // itself (Escape, the overlay, the close button); it does NOT fire when a controlled `open` prop
  // is flipped from OUTSIDE (our own auto-open effect, or the "Share your grade" button), which is
  // every way this modal ever opens. A plain effect on `open` is what actually sees every open.
  useEffect(() => {
    if (open && summary) track("mock_draft_share_modal_shown")
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  if (!summary) return null

  const imagePath = shareImagePath(summary)
  const pageUrl = sharePageUrl(summary)
  const canNativeShare = typeof navigator !== "undefined" && typeof navigator.share === "function"

  const shareText = `I finished ${ordinal(summary.rank)} of ${summary.nTeams} in a ${leagueLabel} mock draft on Credence.`

  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(pageUrl)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 2500)
      track("mock_draft_share_link_copied")
    } catch {
      // Clipboard permission is not guaranteed in every context — the link is still selectable text
      // on the page, so this must never present as a broken modal.
      setCopied(false)
    }
  }

  const nativeShare = async () => {
    if (!canNativeShare) return
    try {
      await navigator.share({ title: "Credence Mock Draft Grade", text: shareText, url: pageUrl })
      track("mock_draft_share_native_share")
    } catch {
      // A user-cancelled share rejects the promise — not an error worth surfacing.
    }
  }

  const downloadImage = () => track("mock_draft_share_image_downloaded")

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg" data-testid="mock-draft-share-modal">
        <DialogHeader>
          <DialogTitle className="text-[#10b981]">Share your grade</DialogTitle>
        </DialogHeader>

        <img
          src={imagePath}
          alt={`Mock draft grade — ${ordinal(summary.rank)} of ${summary.nTeams}`}
          width={1200}
          height={630}
          className="w-full rounded-md border border-[#262626]"
          data-testid="mock-draft-share-image"
        />

        {/* ⚠️ NOT OPTIONAL, AND NOT BEHIND A CLICK — the modal is a second surface presenting the
            same rank GradeCard does, so it carries the same caveat GradeCard does. */}
        <p className="rounded-md border border-[#262626] bg-[#0a0a0a] px-3 py-2 text-[11px] leading-relaxed text-gray-400">
          {GRADE_CIRCULARITY_NOTE}
        </p>

        <div className="flex flex-wrap gap-2">
          <a href={imagePath} download="credence-mock-draft-grade.png" onClick={downloadImage}>
            <Button size="sm" className="bg-[#10b981] font-semibold text-[#0a0a0a] hover:bg-[#059669]">
              <Download className="mr-1.5 h-3.5 w-3.5" /> Download image
            </Button>
          </a>
          <Button size="sm" variant="outline" onClick={copyLink}>
            <Copy className="mr-1.5 h-3.5 w-3.5" /> {copied ? "Copied!" : "Copy link"}
          </Button>
          {canNativeShare && (
            <Button size="sm" variant="outline" onClick={nativeShare}>
              <Share2 className="mr-1.5 h-3.5 w-3.5" /> Share
            </Button>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
