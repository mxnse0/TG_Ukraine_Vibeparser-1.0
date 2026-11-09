"""Freelancehunt.com — official public JSON API (no token required for reads)."""

from __future__ import annotations

import logging

import httpx

from app.models import Order
from app.parsers.base import BaseParser
from app.utils.text import normalize_space, strip_html
from app.utils.time import parse_datetime

log = logging.getLogger(__name__)


class FreelanceHuntParser(BaseParser):
    name = "freelancehunt"
    title = "Freelancehunt"
    color = "#22c55e"
    default_enabled = True
    max_pages = 3
    api_url = "https://api.freelancehunt.com/v2/projects"

    async def fetch(self, client: httpx.AsyncClient, *, pages: int = 1) -> list[Order]:
        orders: list[Order] = []
        seen: set[str] = set()
        headers: dict[str, str] = {}
        # Reads are public; the token is optional and only needed for bidding.
        for page in range(1, max(1, pages) + 1):
            response = await client.get(
                self.api_url, params={"page[number]": page}, headers=headers
            )
            if response.status_code == 403:
                raise RuntimeError("Freelancehunt API заблокував запит (403)")
            response.raise_for_status()
            payload = response.json()
            items = payload.get("data") or []
            if not items:
                break

            for item in items:
                order = self._parse_item(item)
                if order is None or order.external_id in seen:
                    continue
                seen.add(order.external_id)
                orders.append(order)

            links = payload.get("links") or {}
            if not links.get("next"):
                break
        return orders

    def _parse_item(self, item: dict) -> Order | None:
        try:
            project_id = str(item["id"])
            attrs = item.get("attributes") or {}
            title = normalize_space(attrs.get("name"))
            if not title:
                return None
            url = (((item.get("links") or {}).get("self") or {}).get("web")) or ""
            if not url:
                return None

            budget = attrs.get("budget") or {}
            amount = budget.get("amount")
            currency = budget.get("currency")
            if amount is not None:
                amount = float(amount)
            budget_text, min_uah, max_uah, currency = self.normalize_budget(
                amount, amount, currency
            )

            skills = attrs.get("skills") or []
            tags = [normalize_space(skill.get("name")) for skill in skills if skill.get("name")]
            category = tags[0] if tags else ""

            return Order(
                source=self.name,
                external_id=project_id,
                title=title,
                url=url,
                description=strip_html(attrs.get("description")),
                budget_text=budget_text,
                budget_min=min_uah,
                budget_max=max_uah,
                currency=currency,
                category=category,
                tags=tags[:10],
                published_at=parse_datetime(attrs.get("published_at")),
                raw={"id": project_id, "bid_count": attrs.get("bid_count")},
            )
        except (KeyError, TypeError, ValueError) as exc:
            log.debug("Freelancehunt: skipped malformed item: %s", exc)
            return None
