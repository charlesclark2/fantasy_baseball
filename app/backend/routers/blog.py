"""Blog endpoints.

Public:
  GET /blog/posts               — list published posts (newest first)
  GET /blog/posts/{post_id}     — single post by post_id or slug

Admin:
  GET    /admin/blog/posts               — all posts (draft + published)
  GET    /admin/blog/posts/{post_id}     — single post (any status)
  POST   /admin/blog/posts               — create post
  PUT    /admin/blog/posts/{post_id}     — update post
  DELETE /admin/blog/posts/{post_id}     — delete post
"""

from __future__ import annotations

import datetime
import logging
import os
import re
import uuid

import boto3
from boto3.dynamodb.conditions import Attr
from fastapi import APIRouter, Depends, HTTPException

from app.backend.dependencies import get_admin_user
from app.backend.models.blog import (
    BlogListItem,
    BlogListResponse,
    BlogPost,
    CreatePostRequest,
    UpdatePostRequest,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["blog"])

_REGION = os.getenv("AWS_REGION", "us-east-1")
_BLOG_TABLE = os.getenv("BLOG_POSTS_TABLE", "credence-prod-dynamo-blog-posts")


def _table():
    return boto3.resource("dynamodb", region_name=_REGION).Table(_BLOG_TABLE)


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _slugify(text: str) -> str:
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_-]+", "-", slug)
    slug = re.sub(r"^-+|-+$", "", slug)
    return slug or "untitled"


def _item_to_post(item: dict) -> BlogPost:
    return BlogPost(
        post_id=item["post_id"],
        title=item.get("title", ""),
        slug=item.get("slug", ""),
        content=item.get("content", ""),
        excerpt=item.get("excerpt") or None,
        cover_image_url=item.get("cover_image_url") or None,
        published=bool(item.get("published", False)),
        published_at=item.get("published_at") or None,
        created_at=item.get("created_at", ""),
        updated_at=item.get("updated_at", ""),
        tags=list(item.get("tags") or []),
    )


def _item_to_list_item(item: dict) -> BlogListItem:
    return BlogListItem(
        post_id=item["post_id"],
        title=item.get("title", ""),
        slug=item.get("slug", ""),
        excerpt=item.get("excerpt") or None,
        cover_image_url=item.get("cover_image_url") or None,
        published=bool(item.get("published", False)),
        published_at=item.get("published_at") or None,
        tags=list(item.get("tags") or []),
    )


def _scan_all(filter_expr=None) -> list[dict]:
    table = _table()
    kwargs: dict = {}
    if filter_expr is not None:
        kwargs["FilterExpression"] = filter_expr
    resp = table.scan(**kwargs)
    items = list(resp.get("Items", []))
    while resp.get("LastEvaluatedKey"):
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
        resp = table.scan(**kwargs)
        items.extend(resp.get("Items", []))
    return items


# ── Public endpoints ──────────────────────────────────────────────────────────

@router.get("/blog/posts", response_model=BlogListResponse)
def list_published_posts() -> BlogListResponse:
    """Return all published posts, newest first."""
    try:
        items = _scan_all(Attr("published").eq(True))
    except Exception as exc:
        logger.error("Blog list scan failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to load posts") from exc

    posts = sorted(
        (_item_to_list_item(i) for i in items),
        key=lambda p: p.published_at or "",
        reverse=True,
    )
    return BlogListResponse(posts=posts)


@router.get("/blog/posts/{post_id}", response_model=BlogPost)
def get_post(post_id: str) -> BlogPost:
    """Fetch a single published post by post_id or slug."""
    table = _table()
    try:
        resp = table.get_item(Key={"post_id": post_id})
        item = resp.get("Item")
        if item and item.get("published"):
            return _item_to_post(item)
        # Fallback: treat as slug
        items = _scan_all(Attr("slug").eq(post_id) & Attr("published").eq(True))
        if not items:
            raise HTTPException(status_code=404, detail="Post not found")
        return _item_to_post(items[0])
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Blog get_item failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to load post") from exc


# ── Admin endpoints ───────────────────────────────────────────────────────────

@router.get("/admin/blog/posts", response_model=BlogListResponse)
def admin_list_posts(_: str = Depends(get_admin_user)) -> BlogListResponse:
    """Return all posts (draft + published), newest first."""
    try:
        items = _scan_all()
    except Exception as exc:
        logger.error("Admin blog scan failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to load posts") from exc

    posts = sorted(
        (_item_to_list_item(i) for i in items),
        key=lambda p: p.published_at or "",
        reverse=True,
    )
    return BlogListResponse(posts=posts)


@router.get("/admin/blog/posts/{post_id}", response_model=BlogPost)
def admin_get_post(post_id: str, _: str = Depends(get_admin_user)) -> BlogPost:
    """Fetch a single post regardless of published status."""
    try:
        resp = _table().get_item(Key={"post_id": post_id})
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Failed to load post") from exc
    item = resp.get("Item")
    if not item:
        raise HTTPException(status_code=404, detail="Post not found")
    return _item_to_post(item)


@router.post("/admin/blog/posts", response_model=BlogPost, status_code=201)
def create_post(body: CreatePostRequest, _: str = Depends(get_admin_user)) -> BlogPost:
    now = _now_iso()
    post_id = str(uuid.uuid4())
    slug = body.slug.strip() if body.slug else _slugify(body.title)
    item: dict = {
        "post_id": post_id,
        "title": body.title,
        "slug": slug,
        "content": body.content,
        "excerpt": body.excerpt or "",
        "cover_image_url": body.cover_image_url or "",
        "published": body.published,
        "published_at": now if body.published else "",
        "created_at": now,
        "updated_at": now,
        "tags": body.tags,
    }
    try:
        _table().put_item(Item=item)
    except Exception as exc:
        logger.error("Blog put_item failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to create post") from exc
    return _item_to_post(item)


@router.put("/admin/blog/posts/{post_id}", response_model=BlogPost)
def update_post(
    post_id: str, body: UpdatePostRequest, _: str = Depends(get_admin_user)
) -> BlogPost:
    table = _table()
    try:
        resp = table.get_item(Key={"post_id": post_id})
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Failed to load post") from exc

    item = resp.get("Item")
    if not item:
        raise HTTPException(status_code=404, detail="Post not found")

    now = _now_iso()
    was_published = bool(item.get("published", False))
    will_publish = body.published if body.published is not None else was_published

    updates: dict = {"updated_at": now}
    if body.title is not None:
        updates["title"] = body.title
    if body.slug is not None:
        updates["slug"] = body.slug
    if body.content is not None:
        updates["content"] = body.content
    if body.excerpt is not None:
        updates["excerpt"] = body.excerpt
    if body.cover_image_url is not None:
        updates["cover_image_url"] = body.cover_image_url
    if body.published is not None:
        updates["published"] = body.published
    if body.tags is not None:
        updates["tags"] = body.tags

    if will_publish and not was_published:
        updates["published_at"] = now
    elif not will_publish:
        updates["published_at"] = ""

    expr_parts: list[str] = []
    expr_names: dict = {}
    expr_values: dict = {}
    for i, (k, v) in enumerate(updates.items()):
        name_key = f"#f{i}"
        val_key = f":v{i}"
        expr_parts.append(f"{name_key} = {val_key}")
        expr_names[name_key] = k
        expr_values[val_key] = v

    try:
        updated = table.update_item(
            Key={"post_id": post_id},
            UpdateExpression="SET " + ", ".join(expr_parts),
            ExpressionAttributeNames=expr_names,
            ExpressionAttributeValues=expr_values,
            ReturnValues="ALL_NEW",
        )
    except Exception as exc:
        logger.error("Blog update_item failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to update post") from exc

    return _item_to_post(updated["Attributes"])


@router.delete("/admin/blog/posts/{post_id}", status_code=204)
def delete_post(post_id: str, _: str = Depends(get_admin_user)) -> None:
    try:
        _table().delete_item(Key={"post_id": post_id})
    except Exception as exc:
        logger.error("Blog delete_item failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to delete post") from exc
