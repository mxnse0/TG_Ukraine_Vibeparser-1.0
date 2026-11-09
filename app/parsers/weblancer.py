"""Weblancer.net — HTML job list."""

from __future__ import annotations

import logging
import re
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from app.models import Order
from app.parsers.base import BaseParser
from app.utils.text import normalize_space, parse_budget, strip_html
from app.utils.time import parse_datetime, parse_relative_date

log = logging.getLogger(__name__)

_ID_RE = re.compile(r"-(\d+)/?$")
_DATE_RE = re.compile(r"\b(\d{2}\.\d{2}\.\d{4})\b")


class WeblancerParser(BaseParser):
    name = "weblancer"
    title = "Weblancer"
    color = "#3b82f6"
    default_enabled = True
    max_pages = 2
    base_url = "https://www.weblancer.net"
    list_url = "https://www.weblancer.net/ua/freelance/"

    async def fetch(self, client: httpx.AsyncClient, *, pages: int = 1) -> list[Order]:
        orders: list[Order] = []
        seen: set[str] = set()
        for page in range(1, max(1, pages) + 1):
            params = {"page": page} if page > 1 else None
            response = await client.get(self.list_url, params=params)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "lxml")
            articles = soup.find_all("article")
            if not articles:
                raise RuntimeError("Weblancer: не знайдено жодної картки замовлення")
            for article in articles:
                order = self._parse_article(article)
                if order is None or order.external_id in seen:
                    continue
                seen.add(order.external_id)
                orders.append(order)
            if len(articles) < 10:
                break
        return orders

    def _parse_article(self, article) -> Order | None:
        title_link = article.select_one("h2 a[href]")
        if title_link is None:
            return None
        href = title_link.get("href", "")
        title = normalize_space(title_link.get_text(" ", strip=True))
        if not title or "/freelance/" not in href:
            return None

        match = _ID_RE.search(href)
        external_id = match.group(1) if match else self.stable_id(href)

        budget_el = article.select_one("span.text-green-600")
        budget_raw = normalize_space(budget_el.get_text(" ", strip=True)) if budget_el else ""
        budget = parse_budget(budget_raw, rates=self.rates)

        desc_el = article.select_one("p.text-gray-600")
        description = strip_html(desc_el.get_text(" ", strip=True)) if desc_el else ""

        tags: list[str] = []
        for tag_link in article.select("div.flex.flex-wrap.gap-2 a"):
            tag = normalize_space(tag_link.get_text(" ", strip=True))
            if tag and tag not in tags:
                tags.append(tag)

        footer_text = normalize_space(article.get_text(" ", strip=True))
        date_match = _DATE_RE.search(footer_text)
        published = parse_datetime(date_match.group(1)) if date_match else None

        return Order(
            source=self.name,
            external_id=external_id,
            title=title,
            url=urljoin(self.base_url, href),
            description=description,
            budget_text=budget_raw,
            budget_min=budget.min_uah,
            budget_max=budget.max_uah,
            currency=budget.currency,
            category=tags[0] if tags else "",
            tags=tags[:10],
            published_at=published,
            raw={},
        )
