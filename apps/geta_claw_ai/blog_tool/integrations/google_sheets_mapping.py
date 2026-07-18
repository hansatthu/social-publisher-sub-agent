from __future__ import annotations

from datetime import datetime
from typing import Any


HEADERS = [
    "id",
    "created_at",
    "created_date",
    "created_month",
    "keyword",
    "title",
    "slug",
    "meta_description",
    "language",
    "category_name",
    "status",
    "wp_post_id",
    "wp_post_url",
    "seo_score",
    "seo_notes",
]


def article_to_row(article: Any) -> list[str]:
    created_at: datetime | None = article.created_at
    created_at_value = created_at.strftime("%Y-%m-%d %H:%M:%S") if created_at else ""
    created_date_value = created_at.strftime("%Y-%m-%d") if created_at else ""
    created_month_value = created_at.strftime("%Y-%m") if created_at else ""

    status_val = getattr(article.status, "value", str(article.status)) if article.status else ""

    return [
        str(article.id),
        created_at_value,
        created_date_value,
        created_month_value,
        article.keyword or "",
        article.title or "",
        article.slug or "",
        article.meta_description or "",
        article.language or "",
        article.category_name or "",
        status_val,
        str(article.wp_post_id or ""),
        article.wp_post_url or "",
        str(article.seo_score) if getattr(article, "seo_score", None) is not None else "",
        article.seo_notes or "",
    ]


def article_to_row_dict(article: Any) -> dict[str, str]:
    return dict(zip(HEADERS, article_to_row(article)))