"""Domain models shared by parsers, storage, bot and renderer."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class Order:
    source: str
    external_id: str
    title: str
    url: str
    description: str = ""
    budget_text: str = ""
    budget_min: float | None = None  # normalised to UAH
    budget_max: float | None = None  # normalised to UAH
    currency: str | None = None
    category: str = ""
    tags: list[str] = field(default_factory=list)
    published_at: datetime | None = None
    raw: dict = field(default_factory=dict, repr=False)


@dataclass(slots=True)
class LibraryItem:
    id: int
    kind: str  # resume | template
    title: str
    text: str | None
    file_id: str | None
    file_name: str | None
    mime_type: str | None
    local_path: str | None
    is_default: bool
    created_at: str

    @property
    def has_file(self) -> bool:
        return bool(self.file_id)

    @property
    def is_text(self) -> bool:
        return bool(self.text) and not self.file_id


@dataclass(slots=True)
class Filters:
    keywords: list[str]
    exclude_keywords: list[str]
    min_budget: float = 0.0
    max_budget: float = 0.0
    skip_no_budget: bool = False

    def matches(self, order: Order) -> bool:
        haystack = " ".join(
            [
                order.title,
                order.description,
                order.category,
                " ".join(order.tags),
            ]
        ).casefold()

        if self.keywords and not any(word in haystack for word in self.keywords):
            return False

        if self.exclude_keywords and any(word in haystack for word in self.exclude_keywords):
            return False

        if self.min_budget > 0:
            if order.budget_max is not None:
                if order.budget_max < self.min_budget:
                    return False
            elif order.budget_min is not None:
                if order.budget_min < self.min_budget:
                    return False
            elif self.skip_no_budget:
                return False

        if self.max_budget > 0:
            if order.budget_min is not None and order.budget_min > self.max_budget:
                return False
            if order.budget_min is None and order.budget_max is not None:
                if order.budget_max > self.max_budget:
                    return False
            if order.budget_min is None and order.budget_max is None and self.skip_no_budget:
                return False

        if self.skip_no_budget and order.budget_min is None and order.budget_max is None:
            return False

        return True


@dataclass(slots=True)
class CollectResult:
    fetched: int = 0
    new: int = 0
    matched: int = 0
    notified: int = 0
    skipped: int = 0
    errors: dict[str, str] = field(default_factory=dict)
    duration: float = 0.0
    first_run: bool = False
    busy: bool = False
