"""Collector orchestration: baseline, dedupe and notifications."""

from __future__ import annotations

import pytest

from app.config import Settings
from app.models import Order
from app.services.collector import Collector


class FakeParser:
    name = "freelancehunt"
    max_pages = 1

    def __init__(self, orders):
        self.orders = orders

    async def fetch(self, client, *, pages=1):
        return list(self.orders)


class FakeNotifier:
    def __init__(self):
        self.orders = []
        self.texts = []

    async def notify_orders(self, items):
        self.orders.extend(items)
        return len(items)

    async def send_text(self, text, keyboard=None):
        self.texts.append(text)
        return 1


def make_order(external_id: str, **overrides) -> Order:
    data = dict(
        source="freelancehunt",
        external_id=external_id,
        title=f"Python order {external_id}",
        url=f"https://freelancehunt.com/project/{external_id}",
        description="Потрібен aiogram бот",
        budget_text="5 000 UAH",
        budget_min=5000.0,
        budget_max=5000.0,
        currency="UAH",
    )
    data.update(overrides)
    return Order(**data)


@pytest.fixture
def config(tmp_path):
    return Settings(data_dir=tmp_path, db_path=tmp_path / "db.sqlite", poll_interval=20)


async def _collector(monkeypatch, db, config, parser, notifier):
    monkeypatch.setattr(
        "app.services.collector.build_parsers", lambda rates=None: {parser.name: parser}
    )
    collector = Collector(config, db, notifier)
    try:
        yield collector
    finally:
        await collector.close()


@pytest.mark.asyncio
async def test_first_poll_is_silent_baseline(monkeypatch, db, config) -> None:
    parser = FakeParser([make_order("1"), make_order("2")])
    notifier = FakeNotifier()
    gen = _collector(monkeypatch, db, config, parser, notifier)
    collector = await gen.__anext__()
    try:
        result = await collector.collect_once()
    finally:
        await gen.aclose()

    assert result.new == 2
    assert result.first_run is True
    assert result.notified == 0
    assert notifier.orders == []
    assert await db.count_orders() == 2
    assert await db.get_bool("first_run_done") is True
    # Baseline orders are stored as already processed.
    rows = await db.recent_orders(limit=10)
    assert all(row["notified"] == 1 for row in rows)


@pytest.mark.asyncio
async def test_second_poll_notifies_only_new(monkeypatch, db, config) -> None:
    notifier = FakeNotifier()
    parser = FakeParser([make_order("1")])
    gen = _collector(monkeypatch, db, config, parser, notifier)
    collector = await gen.__anext__()
    try:
        await collector.collect_once()  # baseline

        parser.orders = [make_order("1"), make_order("2")]
        result = await collector.collect_once()
    finally:
        await gen.aclose()

    assert result.new == 1
    assert result.matched == 1
    assert result.notified == 1
    assert [order.external_id for _, order in notifier.orders] == ["2"]
    assert await db.count_orders() == 2


@pytest.mark.asyncio
async def test_keyword_filter_suppresses_notification(monkeypatch, db, config) -> None:
    notifier = FakeNotifier()
    parser = FakeParser([make_order("1")])
    gen = _collector(monkeypatch, db, config, parser, notifier)
    collector = await gen.__anext__()
    try:
        await collector.collect_once()  # baseline
        await db.set_setting("keywords", "дизайн")

        parser.orders = [make_order("1"), make_order("2")]
        result = await collector.collect_once()
    finally:
        await gen.aclose()

    assert result.new == 1
    assert result.matched == 0
    assert result.notified == 0
    assert notifier.orders == []


@pytest.mark.asyncio
async def test_source_error_is_reported_and_retried(monkeypatch, db, config) -> None:
    class BrokenParser(FakeParser):
        async def fetch(self, client, *, pages=1):
            raise RuntimeError("boom")

    notifier = FakeNotifier()
    gen = _collector(monkeypatch, db, config, BrokenParser([]), notifier)
    collector = await gen.__anext__()
    try:
        result = await collector.collect_once()
    finally:
        await gen.aclose()

    assert "freelancehunt" in result.errors
    assert "boom" in result.errors["freelancehunt"]
    states = await db.source_states()
    assert states["freelancehunt"]["last_error"]
    assert states["freelancehunt"]["last_ok"] is None
