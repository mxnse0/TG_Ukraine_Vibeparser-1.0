"""Parser base class and shared helpers."""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from typing import Any

import httpx

from app.models import Order
from app.utils.text import format_money, normalize_space


class ParserError(RuntimeError):
    pass


def node_text(node, tag: str) -> str:
    """Read the text of the first child tag (BeautifulSoup, RSS/XML safe)."""
    child = node.find(tag) if node is not None else None
    if child is None:
        return ""
    return normalize_space(child.get_text(" ", strip=True))


class BaseParser(ABC):
    name: str = ""
    title: str = ""
    color: str = "#2563eb"
    default_enabled: bool = True
    max_pages: int = 1

    def __init__(self, rates: dict[str, float] | None = None) -> None:
        self.rates = rates or {"UAH": 1.0}

    @abstractmethod
    async def fetch(self, client: httpx.AsyncClient, *, pages: int = 1) -> list[Order]:
        raise NotImplementedError

    # ------------------------------------------------------------------ helpers
    def normalize_budget(
        self,
        amount_min: float | None,
        amount_max: float | None,
        currency: str | None,
        *,
        text: str = "",
    ) -> tuple[str, float | None, float | None, str | None]:
        currency = (currency or "UAH").upper()
        rate = self.rates.get(currency, 1.0)
        min_uah = round(amount_min * rate, 2) if amount_min is not None else None
        max_uah = round(amount_max * rate, 2) if amount_max is not None else None
        if not text:
            if amount_min is not None and amount_max is not None and amount_min != amount_max:
                text = f"{format_money(amount_min, currency)} – {format_money(amount_max, currency)}"
            elif amount_min is not None:
                text = format_money(amount_min, currency)
        return text, min_uah, max_uah, currency

    @staticmethod
    def stable_id(value: str) -> str:
        return hashlib.sha1(value.encode("utf-8", "ignore")).hexdigest()[:16]

    @staticmethod
    def make_order(**kwargs: Any) -> Order:
        return Order(**kwargs)
