"""Kwork.ru — optional HTML parser (the site is not reachable from every network).

Kwork changes its markup periodically, so the parser tries several card
selectors and falls back to detecting project links. If the layout changes
again, the source health panel will show a clear error instead of silently
returning nothing.
"""

from __future__ import annotations

import logging
import re

import httpx
from bs4 import BeautifulSoup, Tag

from app.models import Order
from app.parsers.base import BaseParser
from app.utils.text import normalize_space, parse_budget, strip_html
from app.utils.time import parse_datetime, parse_relative_date

log = logging.getLogger(__name__)

_ID_RE = re.compile(r"/projects/(\d+)")
_CARD_SELECTORS = (
    "div.wants-card",
    "div.wants-card__wrapper",
    "article.wants-card",
    "div[data-id][class*='card']",
    "article[data-id]",
)


class KworkParser(BaseParser):
    name = "kwork"
    title = "Kwork"
    color = "#ef4444"
    default_enabled = False
    max_pages = 1
    list_url = "https://kwork.ru/projects"

    async def fetch(self, client: httpx.AsyncClient, *, pages: int = 1) -> list[Order]:
        response = await client.get(self.list_url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "lxml")

        cards: list[Tag] = []
        for selector in _CARD_SELECTORS:
            cards = soup.select(selector)
            if cards:
                break

        if not cards:
            cards = self._cards_from_links(soup)
        if not cards:
            raise RuntimeError("Kwork: не вдалося розпізнати картки (змінилася розмітка)")

        orders: list[Order] = []
        seen: set[str] = set()
        for card in cards:
            order = self._parse_card(card)
            if order is None or order.external_id in seen:
                continue
            seen.add(order.external_id)
            orders.append(order)
        return orders

    @staticmethod
    def _cards_from_links(soup: BeautifulSoup) -> list[Tag]:
        cards: list[Tag] = []
        used: set[int] = set()
        for link in soup.select("a[href*='/projects/']"):
            if not _ID_RE.search(link.get("href", "")):
                continue
            parent = link
            for _ in range(4):
                parent = parent.parent  # type: ignore[assignment]
                if not isinstance(parent, Tag):
                    break
                if len(parent.get_text(" ", strip=True)) > 80:
                    if id(parent) not in used:
                        used.add(id(parent))
                        cards.append(parent)
                    break
        return cards

    def _parse_card(self, card: Tag) -> Order | None:
        link = card.select_one("a[href*='/projects/']")
        if link is None:
            return None
        href = link.get("href", "")
        match = _ID_RE.search(href)
        if not match:
            return None

        title = normalize_space(link.get_text(" ", strip=True))
        if not title or len(title) < 3:
            heading = card.select_one("h1, h2, h3, [class*='title']")
            title = normalize_space(heading.get_text(" ", strip=True)) if heading else ""
        if not title:
            return None

        desc_el = card.select_one(
            "[class*='description'], [class*='desc'], .wants-card__description-text"
        )
        description = strip_html(desc_el.get_text(" ", strip=True)) if desc_el else ""
        if not description:
            text = normalize_space(card.get_text(" ", strip=True))
            description = text.replace(title, "", 1).strip()[:1500]

        price_el = card.select_one("[class*='price'], .wants-card__price")
        budget_raw = normalize_space(price_el.get_text(" ", strip=True)) if price_el else ""
        if not budget_raw:
            budget_match = re.search(r"\d[\d \u00a0]*(?:[.,]\d+)?\s*(?:₽|руб|грн|\$|€)", description)
            budget_raw = budget_match.group(0) if budget_match else ""
        budget = parse_budget(budget_raw, default_currency="RUB", rates=self.rates)

        published = None
        time_el = card.select_one("time")
        if time_el is not None:
            published = parse_datetime(time_el.get("datetime") or time_el.get_text(" ", strip=True))
        if published is None:
            published = parse_relative_date(normalize_space(card.get_text(" ", strip=True))[:200])

        return Order(
            source=self.name,
            external_id=match.group(1),
            title=title,
            url=href if href.startswith("http") else f"https://kwork.ru{href}",
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
