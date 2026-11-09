"""Shared pytest fixtures."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
import pytest_asyncio

from app.db import Database
from app.models import Order


@pytest.fixture
def sample_order() -> Order:
    return Order(
        source="freelancehunt",
        external_id="12345",
        title="Розробка Telegram-бота на Python",
        url="https://freelancehunt.com/project/test/12345.html",
        description="Потрібен бот з aiogram та SQLite. Бюджет 12 000 UAH.",
        budget_text="12 000 UAH",
        budget_min=12000.0,
        budget_max=12000.0,
        currency="UAH",
        category="Python",
        tags=["Python", "aiogram"],
        published_at=datetime(2026, 11, 8, 10, 0, tzinfo=timezone.utc),
    )


@pytest_asyncio.fixture
async def db(tmp_path):
    database = Database(tmp_path / "test.db")
    await database.connect()
    await database.init()
    try:
        yield database
    finally:
        await database.close()
