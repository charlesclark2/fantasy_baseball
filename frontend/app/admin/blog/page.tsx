"use client"

import { useState, useEffect, useCallback } from "react"
import { useEditor, EditorContent } from "@tiptap/react"
import type { Editor } from "@tiptap/react"
import StarterKit from "@tiptap/starter-kit"
import TiptapImage from "@tiptap/extension-image"
import TiptapLink from "@tiptap/extension-link"
import TiptapUnderline from "@tiptap/extension-underline"
import Placeholder from "@tiptap/extension-placeholder"
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels"
import { Nav } from "@/components/nav"
import { AdminGuard } from "@/components/auth-guard"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { useAuth } from "@/lib/auth-context"
import { apiFetch } from "@/lib/api"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import {
  Bold,
  Italic,
  Underline as UnderlineIcon,
  Strikethrough,
  Heading1,
  Heading2,
  Heading3,
  List,
  ListOrdered,
  Quote,
  Code,
  Minus,
  Link2,
  ImageIcon,
  ArrowLeft,
  Plus,
  Trash2,
  Save,
  Globe,
  EyeOff,
  FileText,
} from "lucide-react"

// ── Types ─────────────────────────────────────────────────────────────────────

type BlogListItem = {
  post_id: string
  title: string
  slug: string
  excerpt?: string | null
  published: boolean
  published_at?: string | null
  tags: string[]
}

type BlogPost = BlogListItem & {
  content: string
  cover_image_url?: string | null
  created_at: string
  updated_at: string
}

type Draft = {
  post_id: string  // empty string = new post
  title: string
  slug: string
  content: string
  excerpt: string
  cover_image_url: string
  tags: string
  published: boolean
}

// ── Toolbar ───────────────────────────────────────────────────────────────────

function Toolbar({ editor }: { editor: Editor }) {
  const setLink = useCallback(() => {
    const prev = editor.getAttributes("link").href as string | undefined
    const url = window.prompt("Link URL:", prev ?? "https://")
    if (url === null) return
    if (url === "") {
      editor.chain().focus().extendMarkRange("link").unsetLink().run()
      return
    }
    editor.chain().focus().extendMarkRange("link").setLink({ href: url }).run()
  }, [editor])

  const addImage = useCallback(() => {
    const url = window.prompt("Image URL:")
    if (url) editor.chain().focus().setImage({ src: url }).run()
  }, [editor])

  function btn(active: boolean, title: string, onClick: () => void, children: React.ReactNode) {
    return (
      <button
        key={title}
        type="button"
        title={title}
        onClick={onClick}
        className={`p-1.5 rounded transition-colors ${
          active
            ? "bg-[#10b981] text-[#0a0a0a]"
            : "text-gray-400 hover:text-white hover:bg-[#262626]"
        }`}
      >
        {children}
      </button>
    )
  }

  const sep = (k: string) => (
    <div key={k} className="w-px h-5 bg-[#333] self-center mx-0.5" />
  )

  return (
    <div className="flex flex-wrap items-center gap-0.5 border-b border-[#262626] bg-[#0f0f0f] px-2 py-1.5 sticky top-0 z-10">
      {btn(editor.isActive("bold"), "Bold", () => editor.chain().focus().toggleBold().run(), <Bold className="h-3.5 w-3.5" />)}
      {btn(editor.isActive("italic"), "Italic", () => editor.chain().focus().toggleItalic().run(), <Italic className="h-3.5 w-3.5" />)}
      {btn(editor.isActive("underline"), "Underline", () => editor.chain().focus().toggleUnderline().run(), <UnderlineIcon className="h-3.5 w-3.5" />)}
      {btn(editor.isActive("strike"), "Strikethrough", () => editor.chain().focus().toggleStrike().run(), <Strikethrough className="h-3.5 w-3.5" />)}
      {sep("s1")}
      {btn(editor.isActive("heading", { level: 1 }), "Heading 1", () => editor.chain().focus().toggleHeading({ level: 1 }).run(), <Heading1 className="h-3.5 w-3.5" />)}
      {btn(editor.isActive("heading", { level: 2 }), "Heading 2", () => editor.chain().focus().toggleHeading({ level: 2 }).run(), <Heading2 className="h-3.5 w-3.5" />)}
      {btn(editor.isActive("heading", { level: 3 }), "Heading 3", () => editor.chain().focus().toggleHeading({ level: 3 }).run(), <Heading3 className="h-3.5 w-3.5" />)}
      {sep("s2")}
      {btn(editor.isActive("bulletList"), "Bullet list", () => editor.chain().focus().toggleBulletList().run(), <List className="h-3.5 w-3.5" />)}
      {btn(editor.isActive("orderedList"), "Ordered list", () => editor.chain().focus().toggleOrderedList().run(), <ListOrdered className="h-3.5 w-3.5" />)}
      {btn(editor.isActive("blockquote"), "Blockquote", () => editor.chain().focus().toggleBlockquote().run(), <Quote className="h-3.5 w-3.5" />)}
      {btn(editor.isActive("codeBlock"), "Code block", () => editor.chain().focus().toggleCodeBlock().run(), <Code className="h-3.5 w-3.5" />)}
      {btn(false, "Horizontal rule", () => editor.chain().focus().setHorizontalRule().run(), <Minus className="h-3.5 w-3.5" />)}
      {sep("s3")}
      {btn(editor.isActive("link"), "Link", setLink, <Link2 className="h-3.5 w-3.5" />)}
      {btn(false, "Image", addImage, <ImageIcon className="h-3.5 w-3.5" />)}
    </div>
  )
}

// ── Slugify helper ────────────────────────────────────────────────────────────

function slugify(text: string): string {
  return text
    .toLowerCase()
    .trim()
    .replace(/[^\w\s-]/g, "")
    .replace(/[\s_-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    || "untitled"
}

// ── Editor panel ──────────────────────────────────────────────────────────────

function EditorPanel({
  draft,
  onChange,
}: {
  draft: Draft
  onChange: (html: string) => void
}) {
  const editor = useEditor({
    extensions: [
      StarterKit,
      TiptapUnderline,
      TiptapImage,
      TiptapLink.configure({ openOnClick: false, autolink: false }),
      Placeholder.configure({ placeholder: "Write your post here…" }),
    ],
    content: draft.content,
    editorProps: {
      attributes: {
        class:
          "min-h-[500px] px-5 py-4 focus:outline-none text-sm text-gray-200 leading-relaxed",
      },
    },
    onUpdate: ({ editor: e }) => onChange(e.getHTML()),
  })

  // Sync content when post_id changes (switching posts)
  useEffect(() => {
    if (editor && !editor.isDestroyed) {
      editor.commands.setContent(draft.content || "")
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft.post_id])

  if (!editor) return null

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <Toolbar editor={editor} />
      <div className="flex-1 overflow-y-auto">
        <EditorContent editor={editor} />
      </div>
    </div>
  )
}

// ── Preview panel ─────────────────────────────────────────────────────────────

function PreviewPanel({ draft }: { draft: Draft }) {
  return (
    <div className="flex flex-col h-full overflow-y-auto bg-[#0a0a0a] px-6 py-6">
      <p className="text-xs uppercase tracking-widest text-gray-600 mb-4">Preview</p>
      {draft.cover_image_url && (
        <div
          className="mb-6 h-48 w-full rounded-lg bg-cover bg-center bg-[#141414]"
          style={{ backgroundImage: `url(${draft.cover_image_url})` }}
        />
      )}
      <h1 className="text-2xl font-bold text-white leading-tight mb-2">
        {draft.title || <span className="text-gray-600 italic">Untitled</span>}
      </h1>
      {draft.excerpt && (
        <p className="text-sm text-gray-400 mb-4">{draft.excerpt}</p>
      )}
      {draft.tags && (
        <div className="flex flex-wrap gap-1.5 mb-6">
          {draft.tags.split(",").map((t) => t.trim()).filter(Boolean).map((tag) => (
            <span key={tag} className="rounded px-1.5 py-0.5 text-xs bg-[#10b981]/10 text-[#10b981]">
              {tag}
            </span>
          ))}
        </div>
      )}
      <hr className="border-[#262626] mb-6" />
      <div
        className="blog-content"
        dangerouslySetInnerHTML={{ __html: draft.content || "<p class='text-gray-600 italic text-sm'>Nothing written yet…</p>" }}
      />
    </div>
  )
}

// ── Empty draft factory ───────────────────────────────────────────────────────

function emptyDraft(): Draft {
  return {
    post_id: "",
    title: "",
    slug: "",
    content: "",
    excerpt: "",
    cover_image_url: "",
    tags: "",
    published: false,
  }
}

function postToDraft(post: BlogPost): Draft {
  return {
    post_id: post.post_id,
    title: post.title,
    slug: post.slug,
    content: post.content,
    excerpt: post.excerpt ?? "",
    cover_image_url: post.cover_image_url ?? "",
    tags: post.tags.join(", "),
    published: post.published,
  }
}

// ── Main page ─────────────────────────────────────────────────────────────────

function BlogAdminInner() {
  const { accessToken } = useAuth()
  const qc = useQueryClient()

  const [view, setView] = useState<"list" | "editor">("list")
  const [draft, setDraft] = useState<Draft>(emptyDraft())
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  const postsQuery = useQuery<{ posts: BlogListItem[] }>({
    queryKey: ["admin-blog-posts"],
    queryFn: () => apiFetch("/admin/blog/posts", {}, accessToken),
    staleTime: 0,
  })

  // Load full post content when entering editor for an existing post
  const loadPost = useCallback(async (post_id: string) => {
    const full: BlogPost = await apiFetch(`/admin/blog/posts/${post_id}`, {}, accessToken)
    setDraft(postToDraft(full))
    setView("editor")
  }, [accessToken])

  function startNew() {
    setDraft(emptyDraft())
    setSaveError(null)
    setView("editor")
  }

  function goBack() {
    setView("list")
    setSaveError(null)
    qc.invalidateQueries({ queryKey: ["admin-blog-posts"] })
  }

  async function save(publishOverride?: boolean) {
    setSaving(true)
    setSaveError(null)
    const published = publishOverride !== undefined ? publishOverride : draft.published
    const tags = draft.tags.split(",").map((t) => t.trim()).filter(Boolean)
    const slug = draft.slug || slugify(draft.title)

    try {
      if (!draft.post_id) {
        // Create
        const created: BlogPost = await apiFetch(
          "/admin/blog/posts",
          {
            method: "POST",
            body: JSON.stringify({
              title: draft.title,
              slug,
              content: draft.content,
              excerpt: draft.excerpt,
              cover_image_url: draft.cover_image_url,
              published,
              tags,
            }),
          },
          accessToken
        )
        setDraft(postToDraft(created))
      } else {
        // Update
        const updated: BlogPost = await apiFetch(
          `/admin/blog/posts/${draft.post_id}`,
          {
            method: "PUT",
            body: JSON.stringify({
              title: draft.title,
              slug,
              content: draft.content,
              excerpt: draft.excerpt,
              cover_image_url: draft.cover_image_url,
              published,
              tags,
            }),
          },
          accessToken
        )
        setDraft(postToDraft(updated))
      }
      qc.invalidateQueries({ queryKey: ["admin-blog-posts"] })
    } catch (e: unknown) {
      setSaveError(e instanceof Error ? e.message : "Save failed")
    } finally {
      setSaving(false)
    }
  }

  async function deletePost() {
    if (!draft.post_id) return
    if (!window.confirm(`Delete "${draft.title || "this post"}"? This cannot be undone.`)) return
    setSaving(true)
    try {
      await apiFetch(`/admin/blog/posts/${draft.post_id}`, { method: "DELETE" }, accessToken)
      goBack()
    } catch (e: unknown) {
      setSaveError(e instanceof Error ? e.message : "Delete failed")
      setSaving(false)
    }
  }

  // ── List view ───────────────────────────────────────────────────────────────

  if (view === "list") {
    const posts = postsQuery.data?.posts ?? []
    return (
      <div className="min-h-screen bg-[#0a0a0a]">
        <Nav authenticated activeLink="admin" />
        <main className="mx-auto max-w-4xl px-6 py-10">
          <div className="flex items-center justify-between mb-8">
            <div>
              <h1 className="text-2xl font-bold text-white">Blog Posts</h1>
              <p className="text-sm text-gray-500 mt-1">
                {posts.length} post{posts.length !== 1 ? "s" : ""}
              </p>
            </div>
            <Button
              onClick={startNew}
              className="bg-[#10b981] text-[#0a0a0a] font-semibold hover:bg-[#059669]"
            >
              <Plus className="mr-1.5 h-4 w-4" />
              New Post
            </Button>
          </div>

          {postsQuery.isLoading && (
            <p className="text-sm text-gray-500">Loading…</p>
          )}

          {!postsQuery.isLoading && posts.length === 0 && (
            <div className="py-16 text-center rounded-xl border border-[#262626] bg-[#111]">
              <FileText className="mx-auto h-8 w-8 text-gray-600 mb-3" />
              <p className="text-sm text-gray-500">No posts yet. Create your first one.</p>
            </div>
          )}

          {posts.length > 0 && (
            <div className="divide-y divide-[#262626] rounded-xl border border-[#262626] overflow-hidden">
              {posts.map((post) => (
                <div
                  key={post.post_id}
                  className="flex items-center justify-between gap-4 px-5 py-4 bg-[#111] hover:bg-[#161616] transition-colors cursor-pointer"
                  onClick={() => loadPost(post.post_id)}
                >
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-white truncate">{post.title || "Untitled"}</p>
                    {post.excerpt && (
                      <p className="text-xs text-gray-500 mt-0.5 truncate">{post.excerpt}</p>
                    )}
                    {post.published_at && (
                      <p className="text-xs text-gray-600 mt-0.5">
                        {new Date(post.published_at).toLocaleDateString("en-US", {
                          month: "short", day: "numeric", year: "numeric",
                        })}
                      </p>
                    )}
                  </div>
                  <span
                    className={`shrink-0 rounded px-2 py-0.5 text-xs font-medium ${
                      post.published
                        ? "bg-emerald-500/15 text-emerald-400"
                        : "bg-[#262626] text-gray-500"
                    }`}
                  >
                    {post.published ? "Published" : "Draft"}
                  </span>
                </div>
              ))}
            </div>
          )}
        </main>
      </div>
    )
  }

  // ── Editor view ─────────────────────────────────────────────────────────────

  return (
    <div className="min-h-screen bg-[#0a0a0a] flex flex-col">
      <Nav authenticated activeLink="admin" />

      {/* Editor toolbar bar */}
      <div className="sticky top-[73px] z-20 border-b border-[#262626] bg-[#0a0a0a]/95 backdrop-blur-sm">
        <div className="flex items-center gap-3 px-4 py-2.5">
          <button
            onClick={goBack}
            className="flex items-center gap-1 text-xs text-gray-500 hover:text-white transition-colors"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            Posts
          </button>
          <div className="flex-1" />
          {saveError && (
            <p className="text-xs text-red-400">{saveError}</p>
          )}
          <span
            className={`rounded px-2 py-0.5 text-xs font-medium ${
              draft.published
                ? "bg-emerald-500/15 text-emerald-400"
                : "bg-[#262626] text-gray-500"
            }`}
          >
            {draft.published ? "Published" : "Draft"}
          </span>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => save()}
            disabled={saving}
            className="text-gray-400 hover:text-white hover:bg-[#141414] text-xs"
          >
            <Save className="mr-1 h-3.5 w-3.5" />
            Save
          </Button>
          {draft.published ? (
            <Button
              size="sm"
              variant="ghost"
              onClick={() => save(false)}
              disabled={saving}
              className="text-amber-400 hover:text-amber-300 hover:bg-[#141414] text-xs"
            >
              <EyeOff className="mr-1 h-3.5 w-3.5" />
              Unpublish
            </Button>
          ) : (
            <Button
              size="sm"
              onClick={() => save(true)}
              disabled={saving}
              className="bg-[#10b981] text-[#0a0a0a] font-semibold hover:bg-[#059669] text-xs"
            >
              <Globe className="mr-1 h-3.5 w-3.5" />
              Publish
            </Button>
          )}
          {draft.post_id && (
            <Button
              size="sm"
              variant="ghost"
              onClick={deletePost}
              disabled={saving}
              className="text-red-400 hover:text-red-300 hover:bg-[#141414] text-xs"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          )}
        </div>

        {/* Metadata row */}
        <div className="flex flex-wrap gap-2 px-4 pb-2.5">
          <Input
            value={draft.title}
            onChange={(e) => {
              const title = e.target.value
              setDraft((d) => ({
                ...d,
                title,
                slug: d.slug || slugify(title),
              }))
            }}
            placeholder="Post title"
            className="flex-1 min-w-[200px] h-8 text-sm bg-[#111] border-[#333] text-white placeholder:text-gray-600 focus-visible:ring-[#10b981]"
          />
          <Input
            value={draft.slug}
            onChange={(e) => setDraft((d) => ({ ...d, slug: e.target.value }))}
            placeholder="slug-goes-here"
            className="w-44 h-8 text-xs font-mono bg-[#111] border-[#333] text-gray-400 placeholder:text-gray-600 focus-visible:ring-[#10b981]"
          />
          <Input
            value={draft.excerpt}
            onChange={(e) => setDraft((d) => ({ ...d, excerpt: e.target.value }))}
            placeholder="Excerpt (optional)"
            className="flex-1 min-w-[200px] h-8 text-xs bg-[#111] border-[#333] text-gray-400 placeholder:text-gray-600 focus-visible:ring-[#10b981]"
          />
          <Input
            value={draft.cover_image_url}
            onChange={(e) => setDraft((d) => ({ ...d, cover_image_url: e.target.value }))}
            placeholder="Cover image URL"
            className="flex-1 min-w-[160px] h-8 text-xs bg-[#111] border-[#333] text-gray-400 placeholder:text-gray-600 focus-visible:ring-[#10b981]"
          />
          <Input
            value={draft.tags}
            onChange={(e) => setDraft((d) => ({ ...d, tags: e.target.value }))}
            placeholder="Tags (comma-separated)"
            className="w-52 h-8 text-xs bg-[#111] border-[#333] text-gray-400 placeholder:text-gray-600 focus-visible:ring-[#10b981]"
          />
        </div>
      </div>

      {/* Split pane */}
      <div className="flex-1" style={{ height: "calc(100vh - 180px)" }}>
        <PanelGroup direction="horizontal" className="h-full">
          <Panel defaultSize={55} minSize={30}>
            <div className="h-full overflow-hidden border-r border-[#262626]">
              <EditorPanel
                key={draft.post_id || "new"}
                draft={draft}
                onChange={(html) => setDraft((d) => ({ ...d, content: html }))}
              />
            </div>
          </Panel>
          <PanelResizeHandle className="w-1 bg-[#1a1a1a] hover:bg-[#10b981]/40 cursor-col-resize transition-colors" />
          <Panel defaultSize={45} minSize={20}>
            <div className="h-full overflow-hidden">
              <PreviewPanel draft={draft} />
            </div>
          </Panel>
        </PanelGroup>
      </div>
    </div>
  )
}

export default function BlogAdminPage() {
  return (
    <AdminGuard>
      <BlogAdminInner />
    </AdminGuard>
  )
}
