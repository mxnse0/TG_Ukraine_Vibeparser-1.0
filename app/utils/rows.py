"""Convert aiosqlite order rows into Order objects."""

from __future__ import annotations

import json

from app.models import Order
from app.utils.time import parse_datetime


def row_to_order(row) -> Order:
    try:
        tags = json.loads(row["tags"] or "[]")
    except (TypeError, ValueError):
        tags = []
    return Order(
        source=row["source"],
        external_id=row["external_id"],
        title=row["title"],
        url=row["url"],
        description=row["description"] or "",
        budget_text=row["budget_text"] or "",
        budget_min=row["budget_min"],
        budget_max=row["budget_max"],
        currency=row["currency"],
        category=row["category"] or "",
        tags=tags if isinstance(tags, list) else [],
        published_at=parse_datetime(row["published_at"]),
    )
