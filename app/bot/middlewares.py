"""Global access control: only the configured admin(s) / owner can use the bot."""

from __future__ import annotations

import logging

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.config import Settings
from app.db import Database

log = logging.getLogger(__name__)


class AccessMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: TelegramObject, data: dict):
        user = data.get("event_from_user")
        if user is None:
            return await handler(event, data)

        config: Settings = data["config"]
        db: Database = data["db"]

        allowed_ids = set(config.admin_id_list)
        if not allowed_ids:
            owner = await db.get_setting("owner_id", "")
            if owner.strip().isdigit():
                allowed_ids.add(int(owner))

        # No owner yet: allow the first /start to claim the bot. Everything else
        # stays locked until the owner is known.
        if not allowed_ids:
            if isinstance(event, Message) and (event.text or "").startswith("/start"):
                return await handler(event, data)
            if isinstance(event, CallbackQuery):
                await event.answer("Спочатку власник має надіслати /start", show_alert=True)
                return None
            if isinstance(event, Message):
                await event.answer("⛔ Спочатку власник має надіслати /start.")
            return None

        if user.id not in allowed_ids:
            log.warning("Unauthorized access attempt by user %s", user.id)
            if isinstance(event, Message):
                await event.answer("⛔ Доступ заборонено. Цей бот приватний.")
            elif isinstance(event, CallbackQuery):
                await event.answer("⛔ Доступ заборонено", show_alert=True)
            return None

        return await handler(event, data)
