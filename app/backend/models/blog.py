from __future__ import annotations

from pydantic import BaseModel


class BlogPost(BaseModel):
    post_id: str
    title: str
    slug: str
    content: str
    excerpt: str | None = None
    cover_image_url: str | None = None
    published: bool = False
    published_at: str | None = None
    created_at: str
    updated_at: str
    tags: list[str] = []


class BlogListItem(BaseModel):
    post_id: str
    title: str
    slug: str
    excerpt: str | None = None
    cover_image_url: str | None = None
    published: bool = False
    published_at: str | None = None
    tags: list[str] = []


class BlogListResponse(BaseModel):
    posts: list[BlogListItem]


class CreatePostRequest(BaseModel):
    title: str
    slug: str = ""
    content: str = ""
    excerpt: str | None = None
    cover_image_url: str | None = None
    published: bool = False
    tags: list[str] = []


class UpdatePostRequest(BaseModel):
    title: str | None = None
    slug: str | None = None
    content: str | None = None
    excerpt: str | None = None
    cover_image_url: str | None = None
    published: bool | None = None
    tags: list[str] | None = None
