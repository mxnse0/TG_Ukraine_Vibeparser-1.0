"""Shared helpers for bot handlers."""

from __future__ import annotations

import logging

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from app.bot.keyboards import order_keyboard
from app.config import Settings
from app.services.renderer import Renderer
from app.services.notifier import build_caption
from app.utils.rows import row_to_order

log = logging.getLogger(__name__)


async def send_order_card(
    target: Message,
    row,
    renderer: Renderer,
    config: Settings,
    *,
    auto_bid: bool,
) -> None:
    order = row_to_order(row)
    caption = build_caption(order, config.tz)
    keyboard = order_keyboard(row["id"], row["url"], auto_bid=auto_bid)
    try:
        image = await renderer.render(order)
        from aiogram.types import BufferedInputFile

        await target.answer_photo(
            BufferedInputFile(image, filename=f"order_{row['id']}.jpg"),
            caption=caption,
            reply_markup=keyboard,
        )
    except Exception:  # noqa: BLE001 - text is a safe fallback
        log.exception("Could not send order card %s", row["id"])
        await target.answer(caption, reply_markup=keyboard, disable_web_page_preview=True)


async def safe_edit(
    call: CallbackQuery,
    text: str,
    keyboard: InlineKeyboardMarkup | None = None,
) -> None:
    message = call.message
    if message is None:
        return
    try:
        await message.edit_text(text, reply_markup=keyboard, disable_web_page_preview=True)
    except TelegramBadRequest as exc:
        if "message is not modified" in str(exc):
            return
        try:
            await message.answer(text, reply_markup=keyboard, disable_web_page_preview=True)
        except Exception:  # noqa: BLE001
            log.debug("safe_edit fallback failed", exc_info=True)


def short_error(value: str, limit: int = 120) -> str:
    value = (value or "").strip().replace("\n", " ")
    return value if len(value) <= limit else value[: limit - 1] + "…"
