"""Small text helpers: HTML cleanup, truncation, budget extraction."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass

_WHITESPACE_RE = re.compile(r"[ \t\u00a0]+")
_NEWLINES_RE = re.compile(r"\n{3,}")
_TAGS_RE = re.compile(r"<[^>]+>")
_EMOJI_RE = re.compile(
    "[\U0001f000-\U0001faff\u2600-\u27bf\ufe0f\u200d\u2b00-\u2bff]"
)

CURRENCY_ALIASES: list[tuple[str, str]] = [
    (r"грн|гривн|uah|₴", "UAH"),
    (r"usd|долар|долл|\$", "USD"),
    (r"eur|євро|евро|€", "EUR"),
    (r"gbp|фунт|£", "GBP"),
    (r"pln|злот|zł|zl", "PLN"),
    (r"cad|c\$", "CAD"),
    (r"rub|руб|₽", "RUB"),
]
_CURRENCY_RE = re.compile("|".join(f"(?:{pattern})" for pattern, _ in CURRENCY_ALIASES), re.I)
_BUDGET_WORDS_RE = re.compile(
    r"бюджет|вартіст|стоимост|цена|ціна|оплата|зарплат|гонорар|price|budget|pay",
    re.I,
)
_AMOUNT_RE = re.compile(
    r"(?<![\d.,])(\d{1,3}(?:[ \u00a0]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?)\s*([kк])?",
    re.I,
)
_RANGE_RE = re.compile(
    r"(\d[\d \u00a0]*(?:[.,]\d+)?)\s*(?:-|–|—|до|to)\s*[$€₴]?\s*"
    r"(\d[\d \u00a0]*(?:[.,]\d+)?)",
    re.I,
)


@dataclass(slots=True)
class Budget:
    text: str = ""
    min_uah: float | None = None
    max_uah: float | None = None
    currency: str | None = None


def strip_html(value: str | None) -> str:
    if not value:
        return ""
    value = re.sub(r"<\s*br\s*/?\s*>", "\n", value, flags=re.I)
    value = re.sub(r"</\s*p\s*>", "\n\n", value, flags=re.I)
    value = re.sub(r"</\s*li\s*>", "\n", value, flags=re.I)
    value = _TAGS_RE.sub(" ", value)
    value = html.unescape(value)
    return normalize_space(value)


def normalize_space(value: str | None) -> str:
    if not value:
        return ""
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = value.replace("\u200b", "").replace("\ufeff", "")
    value = _WHITESPACE_RE.sub(" ", value)
    value = "\n".join(line.strip() for line in value.split("\n"))
    value = _NEWLINES_RE.sub("\n\n", value)
    return value.strip()


def clean_for_image(value: str | None) -> str:
    value = normalize_space(strip_html(value))
    value = _EMOJI_RE.sub("", value)
    return normalize_space(value)


def truncate(value: str, limit: int, suffix: str = "…") -> str:
    value = value or ""
    if len(value) <= limit:
        return value
    return value[: max(0, limit - len(suffix))].rstrip() + suffix


def split_terms(value: str | None) -> list[str]:
    if not value:
        return []
    parts = re.split(r"[,;\n]+", value)
    return [part.strip().casefold() for part in parts if part.strip()]


def detect_currency(text: str) -> str | None:
    match = _CURRENCY_RE.search(text)
    if not match:
        return None
    found = match.group(0).lower()
    for pattern, code in CURRENCY_ALIASES:
        if re.search(pattern, found, re.I):
            return code
    return None


def _to_float(raw: str, multiplier_word: str | None) -> float | None:
    raw = raw.replace("\u00a0", "").replace(" ", "")
    raw = raw.replace(",", ".")
    try:
        value = float(raw)
    except ValueError:
        return None
    if multiplier_word:
        value *= 1000
    return value


def parse_budget(
    text: str | None,
    *,
    default_currency: str | None = None,
    rates: dict[str, float] | None = None,
    require_currency: bool = False,
) -> Budget:
    """Extract a budget from free-form text.

    Only parses values that are clearly money: a currency marker or a budget
    keyword must be present. This avoids treating years / "5 days" as money.
    Set ``require_currency`` for long free-form descriptions where a budget
    keyword alone is not a reliable signal.
    """

    if not text:
        return Budget()
    value = normalize_space(strip_html(text))
    currency = detect_currency(value) or default_currency
    if require_currency and not currency:
        return Budget()
    has_budget_word = bool(_BUDGET_WORDS_RE.search(value))
    if not currency and not has_budget_word:
        return Budget()

    rates = rates or {"UAH": 1.0}
    rate = rates.get(currency or "UAH", 1.0)

    min_amount: float | None = None
    max_amount: float | None = None
    raw_text = ""

    range_match = _RANGE_RE.search(value)
    if range_match:
        left = _to_float(range_match.group(1), None)
        right = _to_float(range_match.group(2), None)
        is_year_range = (
            left is not None
            and right is not None
            and 1990 <= left <= 2100
            and 1990 <= right <= 2100
            and not _followed_by_currency(value, range_match.end())
        )
        if left is not None and right is not None and 0 < left <= right and not is_year_range:
            min_amount, max_amount = left, right
            raw_text = f"{_fmt(left)} – {_fmt(right)} {currency or ''}".strip()

    if min_amount is None:
        for match in _AMOUNT_RE.finditer(value):
            amount = _to_float(match.group(1), match.group(2))
            if amount is None or amount < 10:
                continue
            # Skip a year unless it is explicitly followed by a currency.
            if 1990 <= amount <= 2100 and not _followed_by_currency(value, match.end()):
                continue
            # "200K+" is a market size / average check, not a budget.
            if match.group(2) and value[match.end() : match.end() + 1] == "+":
                continue
            min_amount = max_amount = amount
            raw_text = f"{_fmt(amount)} {currency or ''}".strip()
            break

    if min_amount is None:
        return Budget(currency=currency)

    return Budget(
        text=raw_text,
        min_uah=round(min_amount * rate, 2),
        max_uah=round(max_amount * rate, 2) if max_amount is not None else None,
        currency=currency,
    )


def _followed_by_currency(value: str, pos: int) -> bool:
    tail = value[pos : pos + 12].lstrip().lower()
    return bool(tail) and bool(_CURRENCY_RE.match(tail))


def _fmt(value: float) -> str:
    if value.is_integer():
        return f"{int(value):,}".replace(",", " ")
    return f"{value:,.2f}".replace(",", " ")


def format_money(value: float | None, currency: str | None) -> str:
    if value is None:
        return ""
    return f"{_fmt(value)} {currency or 'UAH'}".strip()


def html_escape(value: str | None, *, quote: bool = False) -> str:
    return html.escape(value or "", quote=quote)
