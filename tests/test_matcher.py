"""Tests for order filtering."""

from __future__ import annotations

from app.models import Filters, Order


def make_order(**overrides) -> Order:
    data = dict(
        source="freelancehunt",
        external_id="1",
        title="Python Telegram bot",
        url="https://example.com/1",
        description="Потрібен aiogram бот",
        budget_text="5000 UAH",
        budget_min=5000.0,
        budget_max=5000.0,
        currency="UAH",
        category="Розробка",
        tags=["Python"],
    )
    data.update(overrides)
    return Order(**data)


def test_no_filters_matches_everything() -> None:
    assert Filters(keywords=[], exclude_keywords=[]).matches(make_order())


def test_keyword_match_is_case_insensitive() -> None:
    filters = Filters(keywords=["telegram"], exclude_keywords=[])
    assert filters.matches(make_order())
    assert not filters.matches(make_order(title="Лендинг", description="", tags=[]))


def test_exclude_keywords_win() -> None:
    filters = Filters(keywords=["python"], exclude_keywords=["росія"])
    assert not filters.matches(make_order(description="Python, але росія"))


def test_min_budget_uses_max_of_range() -> None:
    filters = Filters(keywords=[], exclude_keywords=[], min_budget=8000)
    assert filters.matches(make_order(budget_min=5000, budget_max=10000))
    assert not filters.matches(make_order(budget_min=1000, budget_max=2000))


def test_max_budget_uses_min_of_range() -> None:
    filters = Filters(keywords=[], exclude_keywords=[], max_budget=3000)
    assert filters.matches(make_order(budget_min=1000, budget_max=2000))
    assert not filters.matches(make_order(budget_min=4000, budget_max=6000))


def test_skip_no_budget() -> None:
    order = make_order(budget_min=None, budget_max=None, budget_text="")
    assert Filters(keywords=[], exclude_keywords=[]).matches(order)
    assert not Filters(
        keywords=[], exclude_keywords=[], skip_no_budget=True
    ).matches(order)
