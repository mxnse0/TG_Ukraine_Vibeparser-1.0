"""Database storage tests (orders, settings, library, source health)."""

from __future__ import annotations

import pytest

from app.models import Order


@pytest.mark.asyncio
async def test_settings_defaults_and_updates(db) -> None:
    assert await db.get_int("notify_limit", 0) == 12
    assert await db.get_bool("notifications_enabled", False) is True

    await db.set_setting("notify_limit", 5)
    await db.set_setting("notifications_enabled", False)
    assert await db.get_int("notify_limit", 0) == 5
    assert await db.get_bool("notifications_enabled", True) is False

    await db.set_setting("keywords", "python, aiogram")
    assert await db.get_setting("keywords") == "python, aiogram"


@pytest.mark.asyncio
async def test_add_order_deduplicates(db, sample_order) -> None:
    first = await db.add_order(sample_order)
    second = await db.add_order(sample_order)

    assert first is not None
    assert second is None
    assert await db.count_orders() == 1

    row = await db.get_order(first)
    assert row is not None
    assert row["title"] == sample_order.title
    assert row["budget_min"] == 12000


@pytest.mark.asyncio
async def test_recent_orders_and_search(db, sample_order) -> None:
    await db.add_order(sample_order)
    await db.add_order(
        Order(
            source="weblancer",
            external_id="2",
            title="Дизайн лендингу",
            url="https://example.com/2",
            description="Figma, UX",
        )
    )

    rows = await db.recent_orders(limit=10)
    assert len(rows) == 2
    assert rows[0]["title"] == "Дизайн лендингу"

    found = await db.recent_orders(search="AIogram")
    assert len(found) == 1
    assert await db.count_orders_search("figma") == 1
    assert await db.count_orders_search("nothing") == 0

    # SQLite's lower() is ASCII-only; search_text must handle Cyrillic case.
    assert len(await db.recent_orders(search="дизайн")) == 1
    assert await db.count_orders_search("ДИЗАЙН") == 1


@pytest.mark.asyncio
async def test_mark_notified(db, sample_order) -> None:
    order_id = await db.add_order(sample_order)
    assert order_id is not None
    row = await db.get_order(order_id)
    assert row["notified"] == 0

    await db.mark_notified(order_id)
    row = await db.get_order(order_id)
    assert row["notified"] == 1


@pytest.mark.asyncio
async def test_library_defaults_and_deletion(db) -> None:
    first = await db.library_add(kind="resume", title="Python CV", text="Senior Python dev")
    second = await db.library_add(kind="resume", title="Backend CV", file_id="file-1")

    items = await db.library_list("resume")
    assert [item.id for item in items] == [first, second]
    default = await db.library_default("resume")
    assert default is not None and default.id == first

    await db.library_set_default(second)
    default = await db.library_default("resume")
    assert default is not None and default.id == second

    removed = await db.library_delete(second)
    assert removed is not None
    default = await db.library_default("resume")
    assert default is not None and default.id == first


@pytest.mark.asyncio
async def test_source_state_accumulates(db) -> None:
    await db.update_source_state("freelancehunt", ok=True, count=10, new_count=3)
    await db.update_source_state("freelancehunt", ok=True, count=12, new_count=2)
    states = await db.source_states()
    state = states["freelancehunt"]
    assert state["last_count"] == 12
    assert state["total_new"] == 5
    assert state["last_error"] == ""

    await db.update_source_state("freelancehunt", ok=False, error="timeout")
    states = await db.source_states()
    assert states["freelancehunt"]["last_error"] == "timeout"
    assert states["freelancehunt"]["last_ok"] is not None
