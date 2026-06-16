import Link from "next/link"
import { Nav } from "@/components/nav"
import { PenSquare } from "lucide-react"

export const metadata = {
  title: "Blog — Credence Sports",
  description: "Baseball analytics, model methodology, and market structure from Credence Sports.",
}

type BlogListItem = {
  post_id: string
  title: string
  slug: string
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

export default async function BlogPage() {
  const base = process.env.NEXT_PUBLIC_API_URL ?? ""
  const data: { posts: BlogListItem[] } = base
    ? await fetch(`${base}/blog/posts`, { next: { revalidate: 60 } })
        .then((r) => (r.ok ? r.json() : { posts: [] }))
        .catch(() => ({ posts: [] }))
    : { posts: [] }

  const posts = data.posts ?? []

  return (
    <div className="min-h-screen bg-background flex flex-col">
      <Nav />

      <main className="flex-1 mx-auto w-full max-w-3xl px-6 py-12">
        <div className="mb-10">
          <p className="text-xs uppercase tracking-widest text-muted-foreground mb-1">
            Credence Sports · A product of Penumbra Partners
          </p>
          <h1 className="text-3xl font-bold text-foreground">Blog</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Baseball analytics, model methodology, and market structure.
          </p>
        </div>

        {posts.length === 0 ? (
          <div className="py-20 text-center">
            <PenSquare className="mx-auto h-8 w-8 text-muted-foreground mb-4" />
            <p className="text-sm text-muted-foreground">
              No posts yet. Check back soon.
            </p>
            <p className="mt-4 text-sm text-muted-foreground">
              In the meantime, check the{" "}
              <Link href="/faq" className="text-[#10b981] hover:underline">
                FAQ
              </Link>{" "}
              for an overview of how Credence works.
            </p>
          </div>
        ) : (
          <div className="divide-y divide-[#262626]">
            {posts.map((post) => (
              <article key={post.post_id} className="py-8 first:pt-0">
                <Link href={`/blog/${post.post_id}`} className="group block">
                  {post.cover_image_url && (
                    <div
                      className="mb-4 h-48 w-full rounded-lg bg-cover bg-center bg-[#141414]"
                      style={{ backgroundImage: `url(${post.cover_image_url})` }}
                    />
                  )}
                  <h2 className="text-xl font-bold text-white group-hover:text-[#10b981] transition-colors">
                    {post.title}
                  </h2>
                  {post.excerpt && (
                    <p className="mt-2 text-sm leading-relaxed text-gray-400 line-clamp-3">
                      {post.excerpt}
                    </p>
                  )}
                  <div className="mt-3 flex flex-wrap items-center gap-3">
                    {post.published_at && (
                      <span className="text-xs text-gray-500">
                        {formatDate(post.published_at)}
                      </span>
                    )}
                    {post.tags.length > 0 && (
                      <div className="flex flex-wrap gap-1.5">
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
                  </div>
                </Link>
              </article>
            ))}
          </div>
        )}

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
