"""Handler-level smoke tests with mocked Telegram objects."""

from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot.handlers.filters import _filters_view, msg_filter_budget
from app.bot.handlers.orders import msg_custom_reply, msg_search
from app.bot.handlers.settings import _settings_text, _status_text
from app.bot.handlers.start import cmd_start
from app.config import Settings


def make_message(text: str = "", user_id: int = 111) -> AsyncMock:
    message = AsyncMock()
    message.text = text
    message.from_user = SimpleNamespace(id=user_id)
    return message


def make_state(data: dict | None = None) -> AsyncMock:
    state = AsyncMock()
    state.get_data.return_value = data or {}
    return state


@pytest.mark.asyncio
async def test_start_claims_owner(db) -> None:
    config = Settings(admin_ids="", bot_token="")
    message = make_message(user_id=777)

    await cmd_start(message, db, config)

    assert await db.get_setting("owner_id") == "777"
    message.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_start_keeps_existing_owner(db) -> None:
    await db.set_setting("owner_id", "111")
    config = Settings(admin_ids="", bot_token="")
    message = make_message(user_id=777)

    await cmd_start(message, db, config)

    assert await db.get_setting("owner_id") == "111"


@pytest.mark.asyncio
async def test_settings_and_status_views(db) -> None:
    config = Settings(data_dir=db.path.parent, db_path=db.path, bot_token="")
    scheduler = SimpleNamespace(started_at=time.time() - 90)

    text = await _settings_text(db, config)
    assert "Налаштування" in text
    assert "75" in text

    status = await _status_text(db, config, scheduler)
    assert "Статус VibeParser" in status
    assert "Freelancehunt" in status
    assert "1 хв" in status or "хв" in status


@pytest.mark.asyncio
async def test_filters_view(db) -> None:
    await db.set_setting("keywords", "python, aiogram")
    await db.set_setting("min_budget", "5000")
    text, keyboard = await _filters_view(db)

    assert "python" in text
    assert "від 5000 UAH" in text
    assert keyboard.inline_keyboard


@pytest.mark.asyncio
async def test_budget_filter_parses_two_values(db) -> None:
    message = make_message("1000 15000")
    await msg_filter_budget(message, make_state(), db)
    assert await db.get_float("min_budget", 0) == 1000
    assert await db.get_float("max_budget", 0) == 15000


@pytest.mark.asyncio
async def test_budget_filter_parses_thousand_separators(db) -> None:
    message = make_message("1 000 – 15 000")
    await msg_filter_budget(message, make_state(), db)
    assert await db.get_float("min_budget", 0) == 1000
    assert await db.get_float("max_budget", 0) == 15000


@pytest.mark.asyncio
async def test_budget_filter_rejects_min_above_max(db) -> None:
    message = make_message("20000 10000")
    await msg_filter_budget(message, make_state(), db)
    assert "Мінімум більший" in message.answer.await_args.args[0]
    assert await db.get_float("min_budget", 0) == 0


@pytest.mark.asyncio
async def test_search_without_results(db) -> None:
    message = make_message("нічого")
    state = make_state()

    await msg_search(message, db, state)

    state.set_state.assert_awaited()
    assert "нічого не знайдено" in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_custom_reply_flow(db, sample_order) -> None:
    order_id = await db.add_order(sample_order)
    assert order_id is not None

    message = make_message("Добрий день! Готовий взятися.")
    state = make_state({"custom_order_id": order_id})

    await msg_custom_reply(message, state, db, Settings(bot_token=""))

    first_text = message.answer.await_args_list[0].args[0]
    assert "Готовий відгук" in first_text
    assert "Готовий взятися" in first_text
    state.set_data.assert_awaited()
    state.set_state.assert_awaited_with(None)
