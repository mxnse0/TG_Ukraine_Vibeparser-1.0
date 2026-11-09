"""Freelance.ua — Ukrainian freelance board, HTML job list."""

from __future__ import annotations

import logging
import re

import httpx
from bs4 import BeautifulSoup

from app.models import Order
from app.parsers.base import BaseParser
from app.utils.text import normalize_space, parse_budget, strip_html
from app.utils.time import parse_relative_date

log = logging.getLogger(__name__)

_ID_RE = re.compile(r"/orders/(\d+)-")


class FreelanceUaParser(BaseParser):
    name = "freelance_ua"
    title = "Freelance.ua"
    color = "#f59e0b"
    default_enabled = True
    max_pages = 2
    list_url = "https://freelance.ua/orders/"

    async def fetch(self, client: httpx.AsyncClient, *, pages: int = 1) -> list[Order]:
        orders: list[Order] = []
        seen: set[str] = set()
        for page in range(1, max(1, pages) + 1):
            params = {"page": page, "t": 1} if page > 1 else None
            response = await client.get(self.list_url, params=params)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "lxml")
            cards = soup.select("li.j-order")
            if not cards:
                raise RuntimeError("Freelance.ua: не знайдено карток замовлень")
            for card in cards:
                order = self._parse_card(card)
                if order is None or order.external_id in seen:
                    continue
                seen.add(order.external_id)
                orders.append(order)
            if len(cards) < 10:
                break
        return orders

    def _parse_card(self, card) -> Order | None:
        link = card.select_one("header.l-project-title a[href]")
        if link is None:
            return None
        href = link.get("href", "")
        title = normalize_space(link.get_text(" ", strip=True))
        match = _ID_RE.search(href)
        if not title or not match:
            return None

        price_el = card.select_one(".l-price")
        budget_raw = normalize_space(price_el.get_text(" ", strip=True)) if price_el else ""
        budget = parse_budget(budget_raw, default_currency="UAH", rates=self.rates)

        desc_el = card.select_one("article p")
        description = strip_html(desc_el.get_text(" ", strip=True)) if desc_el else ""

        published = None
        for li in card.select("ul.l-item-features li"):
            text = normalize_space(li.get_text(" ", strip=True))
            if not text:
                continue
            parsed = parse_relative_date(text)
            if parsed is not None:
                published = parsed
                break

        return Order(
            source=self.name,
            external_id=match.group(1),
            title=title,
            url=href if href.startswith("http") else f"https://freelance.ua{href}",
            description=description,
            budget_text=budget_raw,
            budget_min=budget.min_uah,
            budget_max=budget.max_uah,
            currency=budget.currency,
            category="",
            tags=[],
            published_at=published,
            raw={},
        )
