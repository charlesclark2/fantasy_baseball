import Link from "next/link"
import { Nav } from "@/components/nav"

export const metadata = {
  title: "Blog — Credence Sports",
}

export default function BlogPage() {
  return (
    <div className="min-h-screen bg-background flex flex-col">
      <Nav />

      <main className="flex-1 mx-auto w-full max-w-3xl px-6 py-12">
        <div className="mb-10">
          <p className="text-xs uppercase tracking-widest text-muted-foreground mb-1">
            Credence Sports · A product of Penumbra Partners
          </p>
          <h1 className="text-3xl font-bold text-foreground">Blog</h1>
        </div>

        <div className="py-20 text-center">
          <p className="text-sm text-muted-foreground">
            Coming soon. We&apos;ll be writing about baseball analytics, model methodology, and market structure.
          </p>
          <p className="mt-4 text-sm text-muted-foreground">
            In the meantime, check the{" "}
            <Link href="/faq" className="text-[#10b981] hover:underline">
              FAQ
            </Link>{" "}
            for an overview of how Credence works.
          </p>
        </div>

        <div className="mt-12 pt-8 border-t border-[#262626] flex gap-6 text-sm text-muted-foreground">
          <Link href="/faq" className="hover:text-foreground transition-colors">
            FAQ
          </Link>
          <Link href="/contact" className="hover:text-foreground transition-colors">
            Contact
          </Link>
          <Link href="/privacy" className="hover:text-foreground transition-colors">
            Privacy Policy
          </Link>
        </div>
      </main>
    </div>
  )
}
