"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { X } from "lucide-react"

const STORAGE_KEY = "cookie-consent-dismissed"

export function CookieBanner() {
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    if (!localStorage.getItem(STORAGE_KEY)) {
      setVisible(true)
    }
  }, [])

  function dismiss() {
    localStorage.setItem(STORAGE_KEY, "1")
    setVisible(false)
  }

  if (!visible) return null

  return (
    <div className="fixed bottom-0 left-0 right-0 z-50 border-t border-[#262626] bg-[#111111]/95 backdrop-blur-sm px-4 py-3">
      <div className="mx-auto flex max-w-4xl items-center justify-between gap-4">
        <p className="text-xs text-gray-400 leading-relaxed">
          We use essential cookies to keep you signed in. No advertising or tracking cookies.{" "}
          <Link href="/privacy#cookies" className="underline underline-offset-2 hover:text-gray-200 transition-colors">
            Learn more
          </Link>
        </p>
        <button
          onClick={dismiss}
          aria-label="Dismiss cookie notice"
          className="shrink-0 rounded p-1 text-gray-500 hover:text-gray-200 hover:bg-white/5 transition-colors"
        >
          <X className="w-4 h-4" />
        </button>
      </div>
    </div>
  )
}
