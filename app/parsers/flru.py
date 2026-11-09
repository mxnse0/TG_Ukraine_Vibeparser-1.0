"""FL.ru — optional RSS source (Russian site, may be blocked in some networks)."""

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

_ID_RE = re.compile(r"/(\d{5,})(?:[/?#]|$)")


class FlRuParser(BaseParser):
    name = "flru"
    title = "FL.ru"
    color = "#64748b"
    default_enabled = False
    max_pages = 1
    rss_url = "https://www.fl.ru/rss/all.xml"

    async def fetch(self, client: httpx.AsyncClient, *, pages: int = 1) -> list[Order]:
        response = await client.get(self.rss_url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "xml")
        items = soup.find_all("item")
        if not items:
            raise RuntimeError("FL.ru: RSS порожній або недоступний")

        orders: list[Order] = []
        seen: set[str] = set()
        for item in items:
            title = normalize_space(node_text(item, "title"))
            link = normalize_space(node_text(item, "link"))
            if not title or not link:
                continue
            match = _ID_RE.search(link)
            external_id = match.group(1) if match else self.stable_id(link)
            if external_id in seen:
                continue
            seen.add(external_id)

            description = strip_html(node_text(item, "description"))
            budget = parse_budget(f"{title} {description}", default_currency="RUB", rates=self.rates)
            categories = [
                normalize_space(cat.get_text(" ", strip=True))
                for cat in item.find_all("category")
            ]
            categories = [c for c in categories if c]
            orders.append(
                Order(
                    source=self.name,
                    external_id=external_id,
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
