import { notFound } from "next/navigation"
import Link from "next/link"
import { Nav } from "@/components/nav"
import { ArrowLeft } from "lucide-react"

type BlogPost = {
  post_id: string
  title: string
  slug: string
  content: string
  excerpt?: string | null
  cover_image_url?: string | null
  published_at?: string | null
  tags: string[]
}

function formatDate(iso: string | null | undefined): string {
  if (!iso) return ""
  return new Date(iso).toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
  })
}

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  const base = process.env.NEXT_PUBLIC_API_URL ?? ""
  if (!base) return {}
  const post: BlogPost | null = await fetch(`${base}/blog/posts/${id}`, {
    next: { revalidate: 300 },
  })
    .then((r) => (r.ok ? r.json() : null))
    .catch(() => null)

  if (!post) return {}
  return {
    title: `${post.title} — Credence Sports`,
    description: post.excerpt ?? undefined,
  }
}

export default async function BlogPostPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  const base = process.env.NEXT_PUBLIC_API_URL ?? ""
  const post: BlogPost | null = base
    ? await fetch(`${base}/blog/posts/${id}`, { next: { revalidate: 300 } })
        .then((r) => (r.ok ? r.json() : null))
        .catch(() => null)
    : null

  if (!post) notFound()

  return (
    <div className="min-h-screen bg-background flex flex-col">
      <Nav />

      <main className="flex-1 mx-auto w-full max-w-3xl px-6 py-12">
        {/* Back link */}
        <Link
          href="/blog"
          className="inline-flex items-center gap-1.5 text-xs text-gray-500 hover:text-[#10b981] transition-colors mb-8"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          All posts
        </Link>

        {/* Cover image */}
        {post.cover_image_url && (
          <div
            className="mb-8 h-64 w-full rounded-xl bg-cover bg-center bg-[#141414]"
            style={{ backgroundImage: `url(${post.cover_image_url})` }}
          />
        )}

        {/* Header */}
        <header className="mb-10">
          {post.tags.length > 0 && (
            <div className="mb-3 flex flex-wrap gap-1.5">
              {post.tags.map((tag) => (
                <span
                  key={tag}
                  className="rounded px-1.5 py-0.5 text-xs bg-[#10b981]/10 text-[#10b981]"
                >
                  {tag}
                </span>
              ))}
            </div>
          )}
          <h1 className="text-3xl font-bold text-white md:text-4xl leading-tight">
            {post.title}
          </h1>
          {post.published_at && (
            <p className="mt-3 text-sm text-gray-500">{formatDate(post.published_at)}</p>
          )}
        </header>

        {/* Body */}
        <div
          className="blog-content"
          dangerouslySetInnerHTML={{ __html: post.content }}
        />

        {/* Footer */}
        <div className="mt-14 pt-8 border-t border-[#262626] flex gap-6 text-sm text-muted-foreground">
          <Link href="/blog" className="hover:text-foreground transition-colors">
            ← All posts
          </Link>
          <Link href="/contact" className="hover:text-foreground transition-colors">
            Contact
          </Link>
        </div>
      </main>
    </div>
  )
}
