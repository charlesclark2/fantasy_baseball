"use client"

import { useState } from "react"
import { useMutation } from "@tanstack/react-query"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Textarea } from "@/components/ui/textarea"
import { Button } from "@/components/ui/button"
import { useToast } from "@/hooks/use-toast"
import { useAuth } from "@/lib/auth-context"
import { apiFetch } from "@/lib/api"

export function ReportDataIssue({ gamePk }: { gamePk: number | null }) {
  const [open, setOpen] = useState(false)
  const [description, setDescription] = useState("")
  const { accessToken, email } = useAuth()
  const { toast } = useToast()

  const mutation = useMutation({
    mutationFn: () =>
      apiFetch(
        "/feedback/data-quality",
        {
          method: "POST",
          body: JSON.stringify({
            page_url: window.location.href,
            game_pk: gamePk,
            user_email: email ?? "",
            description,
          }),
        },
        accessToken
      ),
    onSuccess: () => {
      setOpen(false)
      setDescription("")
      toast({ title: "Report submitted — thank you" })
    },
    onError: () => {
      toast({ title: "Couldn't send report, please try again", variant: "destructive" })
    },
  })

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="text-xs text-gray-600 hover:text-gray-400 transition-colors underline underline-offset-2"
      >
        Report data issue
      </button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="bg-[#141414] border border-[#262626] text-white max-w-md">
          <DialogHeader>
            <DialogTitle className="text-white">Report a data issue</DialogTitle>
          </DialogHeader>
          <Textarea
            placeholder="Describe the issue…"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            className="bg-[#0d0d0d] border-[#262626] text-white placeholder:text-gray-600 min-h-[100px] resize-none"
          />
          <Button
            onClick={() => mutation.mutate()}
            disabled={description.trim() === "" || mutation.isPending}
            className="bg-[#10b981] hover:bg-[#059669] text-[#0a0a0a] font-semibold w-full"
          >
            {mutation.isPending ? "Submitting…" : "Submit"}
          </Button>
        </DialogContent>
      </Dialog>
    </>
  )
}
