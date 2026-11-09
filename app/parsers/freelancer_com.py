"""Freelancer.com — public projects API."""

from __future__ import annotations

import logging

import httpx

from app.models import Order
from app.parsers.base import BaseParser
from app.utils.text import normalize_space, strip_html
from app.utils.time import parse_datetime

log = logging.getLogger(__name__)


class FreelancerComParser(BaseParser):
    name = "freelancer"
    title = "Freelancer.com"
    color = "#f97316"
    default_enabled = True
    max_pages = 1
    api_url = "https://www.freelancer.com/api/projects/0.1/projects/active/"

    async def fetch(self, client: httpx.AsyncClient, *, pages: int = 1) -> list[Order]:
        response = await client.get(
            self.api_url,
            params={
                "limit": 20,
                "offset": 0,
                "full_description": "true",
                "job_details": "true",
                "upgrade_details": "true",
            },
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") != "success":
            raise RuntimeError(f"Freelancer API: {payload.get('message', 'невідома помилка')}")

        orders: list[Order] = []
        seen: set[str] = set()
        for project in (payload.get("result") or {}).get("projects") or []:
            order = self._parse_project(project)
            if order is None or order.external_id in seen:
                continue
            seen.add(order.external_id)
            orders.append(order)
        return orders

    def _parse_project(self, project: dict) -> Order | None:
        try:
            project_id = str(project["id"])
            title = normalize_space(project.get("title"))
            seo_url = (project.get("seo_url") or "").strip("/")
            if not title or not seo_url:
                return None

            currency_info = project.get("currency") or {}
            currency = currency_info.get("code") or "USD"

            budget = project.get("budget") or {}
            amount_min = budget.get("minimum")
            amount_max = budget.get("maximum")
            if amount_min is None:
                hourly = project.get("hourly_project_info") or {}
                amount_min = hourly.get("min_amount")
                amount_max = hourly.get("max_amount")
                if hourly.get("hourly_rate_type"):
                    currency = "USD"

            if amount_min is not None:
                amount_min = float(amount_min)
            if amount_max is not None:
                amount_max = float(amount_max)
            budget_text, min_uah, max_uah, currency = self.normalize_budget(
                amount_min, amount_max, currency
            )

            jobs = project.get("jobs") or []
            tags = [normalize_space(job.get("name")) for job in jobs if job.get("name")]
            category = ""
            if jobs:
                category = normalize_space((jobs[0].get("category") or {}).get("name"))

            return Order(
                source=self.name,
                external_id=project_id,
                title=title,
                url=f"https://www.freelancer.com/projects/{seo_url}",
                description=strip_html(project.get("description") or project.get("preview_description")),
                budget_text=budget_text,
                budget_min=min_uah,
                budget_max=max_uah,
                currency=currency,
                category=category,
                tags=tags[:10],
                published_at=parse_datetime(project.get("time_submitted")),
                raw={"bid_count": (project.get("bid_stats") or {}).get("bid_count")},
            )
        except (KeyError, TypeError, ValueError) as exc:
            log.debug("Freelancer: skipped malformed project: %s", exc)
            return None
