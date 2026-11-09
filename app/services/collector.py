"""Fetch every enabled source, store new orders, match filters and notify."""

from __future__ import annotations

import asyncio
import logging
import time

import httpx

from app.config import Settings
from app.db import Database
from app.models import CollectResult, Order
from app.parsers import build_parsers
from app.services.matcher import load_filters
from app.services.notifier import Notifier
from app.utils.time import utc_iso

log = logging.getLogger(__name__)


class Collector:
    def __init__(self, config: Settings, db: Database, notifier: Notifier | None = None) -> None:
        self.config = config
        self.db = db
        self.notifier = notifier
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(config.http_timeout),
            follow_redirects=True,
            headers={
                "User-Agent": config.user_agent,
                "Accept-Language": "uk-UA,uk;q=0.9,en;q=0.8",
                "Accept": "text/html,application/xhtml+xml,application/json,application/xml;q=0.9,*/*;q=0.8",
            },
        )
        self._lock = asyncio.Lock()
        self.last_run: float | None = None

    async def close(self) -> None:
        await self.client.aclose()

    async def collect_once(self) -> CollectResult:
        if self._lock.locked():
            return CollectResult(busy=True)

        async with self._lock:
            started = time.monotonic()
            self.last_run = time.time()
            result = CollectResult()

            enabled = set(await self.db.get_enabled_sources())
            parsers = build_parsers(self.config.currency_rates)
            active = [parser for name, parser in parsers.items() if name in enabled]
            if not active:
                log.warning("No sources enabled")
                return result

            states_before = await self.db.source_states()
            baseline_sources = {
                parser.name
                for parser in active
                if parser.name not in states_before or not states_before[parser.name]["last_ok"]
            }

            outcomes = await asyncio.gather(*(self._fetch(parser) for parser in active))
            total_before = await self.db.count_orders()
            first_run = not await self.db.get_bool("first_run_done", False) and total_before == 0

            new_items: list[tuple[int, Order]] = []
            baseline_items: list[tuple[int, Order]] = []
            for source, orders, error in outcomes:
                if error:
                    result.errors[source] = error
                    log.warning("%s: %s", source, error)
                result.fetched += len(orders)
                source_new = 0
                for order in orders:
                    order_id = await self.db.add_order(order)
                    if order_id is not None:
                        item = (order_id, order)
                        if source in baseline_sources:
                            baseline_items.append(item)
                        else:
                            new_items.append(item)
                        source_new += 1
                await self.db.update_source_state(
                    source,
                    ok=error is None,
                    count=len(orders),
                    error=error or "",
                    new_count=source_new,
                )

            if baseline_items:
                # First successful poll for a source is a silent baseline, so a
                # freshly added source never floods the chat with old orders.
                await self.db.mark_notified_many([order_id for order_id, _ in baseline_items])

            result.new = len(new_items) + len(baseline_items)
            result.first_run = first_run

            if first_run:
                await self.db.mark_all_notified()
                await self.db.set_setting("first_run_done", "1")
                if self.notifier is not None and result.new:
                    await self.notifier.send_text(
                        "✅ <b>VibeParser запущено</b>\n\n"
                        f"Перший запуск: зібрано <b>{result.new}</b> замовлень із "
                        f"{len(active)} джерел.\n"
                        "Старі замовлення не надсилаю, далі приходитимуть лише нові. "
                        "Переглянути все можна кнопкою «📥 Замовлення»."
                    )
            else:
                await self._notify_new(new_items, result)
                if not await self.db.get_bool("first_run_done", False):
                    await self.db.set_setting("first_run_done", "1")

            await self.db.set_setting("last_poll", utc_iso())
            await self.db.set_setting("last_poll_new", result.new)
            await self.db.set_setting("last_poll_error", "; ".join(result.errors.values())[:500])
            result.duration = time.monotonic() - started
            log.info(
                "Poll finished: fetched=%s new=%s matched=%s notified=%s errors=%s in %.1fs",
                result.fetched,
                result.new,
                result.matched,
                result.notified,
                len(result.errors),
                result.duration,
            )
            return result

    async def _fetch(self, parser) -> tuple[str, list[Order], str | None]:
        started = time.monotonic()
        pages = min(parser.max_pages, self.config.max_pages)
        try:
            orders = await asyncio.wait_for(
                parser.fetch(self.client, pages=pages),
                timeout=max(30.0, self.config.http_timeout * 2),
            )
            log.debug("%s: %s orders in %.2fs", parser.name, len(orders), time.monotonic() - started)
            return parser.name, orders, None
        except asyncio.TimeoutError:
            return parser.name, [], "Таймаут запиту"
        except Exception as exc:  # noqa: BLE001 - report per-source health
            return parser.name, [], f"{type(exc).__name__}: {exc}"[:500]

    async def _notify_new(self, new_items: list[tuple[int, Order]], result: CollectResult) -> None:
        if not new_items:
            return

        filters = await load_filters(self.db)
        matched = [(order_id, order) for order_id, order in new_items if filters.matches(order)]
        result.matched = len(matched)

        notifications_enabled = await self.db.get_bool("notifications_enabled", True)
        limit = max(1, await self.db.get_int("notify_limit", 12))
        to_send = matched[:limit]
        skipped = len(matched) - len(to_send)
        result.skipped = skipped

        if notifications_enabled and self.notifier is not None and to_send:
            result.notified = await self.notifier.notify_orders(to_send)
            if skipped:
                await self.notifier.send_text(
                    f"📥 Ще <b>{skipped}</b> нових замовлень не влізли в ліміт сповіщень. "
                    "Відкрийте «📥 Замовлення», щоб переглянути всі."
                )
        elif not notifications_enabled:
            log.info("Notifications are disabled; %s new orders stored", len(new_items))

        # Everything new is considered processed: matching items were sent or are
        # available in the in-bot list, non-matching items are intentionally silent.
        await self.db.mark_notified_many([order_id for order_id, _ in new_items])
