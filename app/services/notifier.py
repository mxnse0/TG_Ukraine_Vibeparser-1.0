"""Sending order cards and service messages to the bot owner(s)."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)
from aiogram.types import BufferedInputFile, InlineKeyboardMarkup

from app.bot.keyboards import order_keyboard
from app.config import Settings
from app.db import Database
from app.models import Order
from app.services.renderer import Renderer
from app.utils.text import html_escape, truncate
from app.utils.time import human_time

log = logging.getLogger(__name__)


class Notifier:
    def __init__(
        self,
        bot: Bot,
        db: Database,
        renderer: Renderer,
        config: Settings,
    ) -> None:
        self.bot = bot
        self.db = db
        self.renderer = renderer
        self.config = config

    async def admin_ids(self) -> list[int]:
        if self.config.admin_id_list:
            return self.config.admin_id_list
        owner = await self.db.get_setting("owner_id", "")
        if owner.strip().isdigit():
            return [int(owner)]
        return []

    async def notify_orders(self, items: list[tuple[int, Order]]) -> int:
        if not items:
            return 0
        admins = await self.admin_ids()
        if not admins:
            log.warning("No admin/owner configured, cannot send notifications")
            return 0

        sent = 0
        for index, (order_id, order) in enumerate(items):
            try:
                image = await self.renderer.render(order)
                caption = build_caption(order, self.config.tz)
                keyboard = order_keyboard(
                    order_id,
                    order.url,
                    auto_bid=order.source == "freelancehunt" and bool(self.config.freelancehunt_token),
                )
                ok = False
                for chat_id in admins:
                    ok = await self._send_photo(chat_id, order_id, image, caption, keyboard) or ok
                if ok:
                    sent += 1
                    await self.db.mark_notified(order_id)
            except Exception:  # noqa: BLE001 - one bad order must not stop the loop
                log.exception("Failed to notify about order %s", order_id)
            if index < len(items) - 1:
                await asyncio.sleep(0.8)
        return sent

    async def _send_photo(
        self,
        chat_id: int,
        order_id: int,
        image: bytes,
        caption: str,
        keyboard: InlineKeyboardMarkup,
    ) -> bool:
        photo = BufferedInputFile(image, filename=f"order_{order_id}.jpg")
        for attempt in range(2):
            try:
                await self.bot.send_photo(
                    chat_id=chat_id,
                    photo=photo,
                    caption=caption,
                    reply_markup=keyboard,
                )
                return True
            except TelegramRetryAfter as exc:
                wait = int(exc.retry_after) + 1
                log.warning("Telegram flood control: sleeping %ss", wait)
                await asyncio.sleep(wait)
            except TelegramForbiddenError:
                log.warning("Bot was blocked by chat %s", chat_id)
                return False
            except TelegramBadRequest as exc:
                log.warning("send_photo failed (%s), falling back to text", exc)
                return await self._send_text_only(chat_id, caption, keyboard)
            except Exception:  # noqa: BLE001
                log.exception("send_photo failed for chat %s", chat_id)
                if attempt == 0:
                    await asyncio.sleep(1.5)
        return False

    async def _send_text_only(
        self, chat_id: int, text: str, keyboard: InlineKeyboardMarkup
    ) -> bool:
        try:
            await self.bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard)
            return True
        except Exception:  # noqa: BLE001
            log.exception("send_message fallback failed for chat %s", chat_id)
            return False

    async def send_text(
        self, text: str, keyboard: InlineKeyboardMarkup | None = None
    ) -> int:
        admins = await self.admin_ids()
        delivered = 0
        for chat_id in admins:
            try:
                await self.bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard)
                delivered += 1
            except Exception:  # noqa: BLE001
                log.exception("send_text failed for chat %s", chat_id)
        return delivered


def build_caption(order: Order, tz: str) -> str:
    when = human_time(order.published_at, tz)
    link = (
        f'🔗 <a href="{html_escape(order.url, quote=True)}">Відкрити замовлення</a>'
    )

    def compose(title_limit: int, budget_limit: int, desc_limit: int) -> str:
        title = html_escape(truncate(order.title, title_limit))
        budget = html_escape(truncate(order.budget_text or "не вказано", budget_limit))
        category = html_escape(truncate(order.category or "—", 80))
        description = html_escape(truncate(order.description, desc_limit))
        parts = [
            f"🆕 <b>{title}</b>",
            "",
            f"💰 <b>Бюджет:</b> {budget}",
            f"🏷 <b>Категорія:</b> {category}",
            f"🕒 {when}",
        ]
        if description:
            parts += ["", description]
        parts += ["", link]
        return "\n".join(parts)

    # Telegram allows 1024 characters per caption. Rebuild without the
    # description (and then with shorter fields) instead of cutting HTML tags.
    for limits in ((160, 80, 360), (160, 80, 0), (90, 50, 0)):
        caption = compose(*limits)
        if len(caption) <= 1024:
            return caption
    return compose(60, 30, 0)[:1024]
