"""Djinni.co — Ukrainian IT job board RSS (optional source, disabled by default)."""

from __future__ import annotations

import logging
import re

import httpx
from bs4 import BeautifulSoup

from app.models import Order
from app.parsers.base import BaseParser, node_text
from app.utils.text import normalize_space, parse_budget, strip_html
from app.utils.time import parse_datetime

log = logging.getLogger(__name__)

_ID_RE = re.compile(r"/jobs/(\d+)-")


class DjinniParser(BaseParser):
    name = "djinni"
    title = "Djinni"
    color = "#8b5cf6"
    default_enabled = False
    max_pages = 1
    rss_url = "https://djinni.co/jobs/rss/"

    async def fetch(self, client: httpx.AsyncClient, *, pages: int = 1) -> list[Order]:
        response = await client.get(self.rss_url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "xml")
        items = soup.find_all("item")
        if not items:
            raise RuntimeError("Djinni: RSS порожній або змінився формат")

        orders: list[Order] = []
        seen: set[str] = set()
        for item in items[:60]:
            link = normalize_space(node_text(item, "link"))
            title = normalize_space(node_text(item, "title"))
            match = _ID_RE.search(link)
            if not title or not match or match.group(1) in seen:
                continue
            seen.add(match.group(1))
            description = strip_html(node_text(item, "description"))
            budget = parse_budget(description, rates=self.rates, require_currency=True)
            categories = [
                normalize_space(cat.get_text(" ", strip=True))
                for cat in item.find_all("category")
            ]
            categories = [c for c in categories if c]
            orders.append(
                Order(
                    source=self.name,
                    external_id=match.group(1),
                    title=title,
                    url=link,
                    description=description,
                    budget_text=budget.text,
                    budget_min=budget.min_uah,
                    budget_max=budget.max_uah,
                    currency=budget.currency,
                    category=categories[0] if categories else "",
                    tags=categories[:6],
                    published_at=parse_datetime(node_text(item, "pubDate")),
                    raw={},
                )
            )
        return orders
