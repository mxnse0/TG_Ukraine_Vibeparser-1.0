"""Card rendering and notification caption tests."""

from __future__ import annotations

import pytest

from app.config import Settings
from app.models import Order
from app.services.notifier import build_caption
from app.services.renderer import Renderer, demo_order
from app.utils.rows import row_to_order


@pytest.mark.asyncio
async def test_render_demo_card(tmp_path) -> None:
    config = Settings(data_dir=tmp_path, db_path=tmp_path / "db.sqlite")
    config.ensure_dirs()
    renderer = Renderer(config)
    try:
        image = await renderer.render(demo_order())
    finally:
        await renderer.close()

    assert image.startswith(b"\xff\xd8\xff")  # JPEG magic
    assert len(image) > 10_000


def test_caption_escapes_html_and_links() -> None:
    order = Order(
        source="freelancehunt",
        external_id="1",
        title="<b>Python</b> & Telegram",
        url="https://example.com/?a=1&b=2",
        description="Опис <script>alert(1)</script>",
        budget_text="5 000 UAH",
        category="Розробка & боти",
    )
    caption = build_caption(order, "Europe/Kyiv")

    assert "<b>Python</b>" not in caption
    assert "&lt;b&gt;Python&lt;/b&gt;" in caption
    assert "a=1&amp;b=2" in caption
    assert "<script>" not in caption


def test_caption_is_limited_to_telegram_size() -> None:
    order = Order(
        source="freelancehunt",
        external_id="1",
        title="Дуже довга назва " * 40,
        url="https://example.com/1",
        description="Довгий опис " * 500,
        budget_text="1 000 UAH " * 40,
        category="Категорія " * 30,
    )
    caption = build_caption(order, "Europe/Kyiv")
    assert len(caption) <= 1024
    assert caption.endswith("Відкрити замовлення</a>")


def test_row_to_order_roundtrip() -> None:
    row = {
        "source": "weblancer",
        "external_id": "42",
        "title": "Test",
        "url": "https://example.com/42",
        "description": None,
        "budget_text": None,
        "budget_min": None,
        "budget_max": None,
        "currency": None,
        "category": None,
        "tags": '["Python", "Bot"]',
        "published_at": None,
    }
    order = row_to_order(row)
    assert order.tags == ["Python", "Bot"]
    assert order.description == ""
    assert order.source == "weblancer"
