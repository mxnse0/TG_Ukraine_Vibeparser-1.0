"""Smoke tests for bot wiring (no Telegram network access)."""

from __future__ import annotations

from aiogram import Dispatcher

from app.bot.handlers import setup_routers
from app.bot.keyboards import main_menu, order_keyboard, orders_keyboard


def test_routers_register_handlers() -> None:
    dp = Dispatcher()
    setup_routers(dp)
    # start/library/filters/orders/autobid/settings all register something.
    messages = sum(len(router.message.handlers) for router in dp.sub_routers)
    callbacks = sum(len(router.callback_query.handlers) for router in dp.sub_routers)
    assert len(dp.sub_routers) == 6
    assert messages >= 5
    assert callbacks >= 10


def test_keyboards_build() -> None:
    menu = main_menu()
    assert menu.inline_keyboard

    order = order_keyboard(1, "https://example.com/1", auto_bid=True)
    callbacks = [button.callback_data for row in order.inline_keyboard for button in row]
    assert "reply:1" in callbacks
    assert "bid:1" in callbacks

    rows = [
        {
            "id": 1,
            "source": "freelancehunt",
            "title": "Test order",
            "budget_text": "5 000 UAH",
        }
    ]
    listing = orders_keyboard(rows, 0, 1)
    assert listing.inline_keyboard[0][0].callback_data == "order:1"
