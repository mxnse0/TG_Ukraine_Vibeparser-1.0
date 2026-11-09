"""Tests for text and budget helpers."""

from __future__ import annotations

from app.utils.text import (
    detect_currency,
    format_money,
    html_escape,
    normalize_space,
    parse_budget,
    split_terms,
    strip_html,
    truncate,
)

RATES = {"UAH": 1.0, "USD": 41.0, "EUR": 45.0, "RUB": 0.45}


def test_normalize_space_collapses_whitespace() -> None:
    assert normalize_space("  a\t\t b \n\n\n c  ") == "a b\n\nc"
    assert normalize_space(None) == ""


def test_strip_html_keeps_line_breaks() -> None:
    assert strip_html("<p>Hello<br>world</p><p>Second</p>") == "Hello\nworld\n\nSecond"
    assert strip_html(None) == ""


def test_detect_currency() -> None:
    assert detect_currency("1000 грн") == "UAH"
    assert detect_currency("$500") == "USD"
    assert detect_currency("500 €") == "EUR"
    assert detect_currency("без бюджету") is None


def test_parse_budget_single_amount() -> None:
    budget = parse_budget("Бюджет: 5 000 грн", rates=RATES)
    assert budget.min_uah == 5000
    assert budget.max_uah == 5000
    assert budget.currency == "UAH"
    assert "5 000" in budget.text


def test_parse_budget_range_and_conversion() -> None:
    budget = parse_budget("від $1000 до $3500", rates=RATES)
    assert budget.min_uah == 41000
    assert budget.max_uah == 143500
    assert budget.currency == "USD"


def test_parse_budget_ignores_years_and_days() -> None:
    assert parse_budget("2024-2025 роки", rates=RATES).min_uah is None
    assert parse_budget("термін 5 днів", rates=RATES).min_uah is None


def test_parse_budget_year_with_currency_is_money() -> None:
    budget = parse_budget("2024 грн", rates=RATES)
    assert budget.min_uah == 2024


def test_parse_budget_require_currency() -> None:
    assert parse_budget("оплата 5000", rates=RATES).min_uah == 5000
    assert parse_budget("оплата 5000", rates=RATES, require_currency=True).min_uah is None
    assert (
        parse_budget("оплата 5000 грн", rates=RATES, require_currency=True).min_uah
        == 5000
    )


def test_parse_budget_skips_market_size_multiplier() -> None:
    budget = parse_budget("200K+ середній чек, фікс $3000", rates=RATES, require_currency=True)
    assert budget.min_uah == 123000


def test_truncate_and_split_terms() -> None:
    assert truncate("abcdef", 5) == "abcd…"
    assert truncate("abc", 5) == "abc"
    assert split_terms("Python, aiogram;\nTelegram bot") == [
        "python",
        "aiogram",
        "telegram bot",
    ]


def test_format_money_and_html_escape() -> None:
    assert format_money(12000, "UAH") == "12 000 UAH"
    assert format_money(None, "UAH") == ""
    assert html_escape("<b>") == "&lt;b&gt;"
    assert html_escape('a&b="c"', quote=True) == "a&amp;b=&quot;c&quot;"
