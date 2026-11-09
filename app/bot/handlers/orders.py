"""Order list, order cards, search and the reply composer."""

from __future__ import annotations

import html
import math

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.handlers.common import safe_edit, send_order_card
from app.bot.keyboards import (
    main_menu,
    orders_keyboard,
    reply_keyboard,
    reply_result_keyboard,
)
from app.bot.states import ReplyStates, SearchStates
from app.config import Settings
from app.db import Database
from app.services.renderer import Renderer
from app.utils.text import truncate

router = Router(name="orders")

PAGE_SIZE = 5


def _auto_bid(source: str, config: Settings) -> bool:
    return source == "freelancehunt" and bool(config.freelancehunt_token)


@router.callback_query(F.data.startswith("orders:"))
async def cb_orders(
    call: CallbackQuery, db: Database, state: FSMContext
) -> None:
    await call.answer()
    await state.update_data(search="")
    page = _to_int(call.data.split(":", 1)[1], 0)
    await _show_orders(call, db, page=page)


@router.callback_query(F.data.startswith("searchpage:"))
async def cb_search_page(call: CallbackQuery, db: Database, state: FSMContext) -> None:
    await call.answer()
    data = await state.get_data()
    search = str(data.get("search") or "")
    page = _to_int(call.data.split(":", 1)[1], 0)
    await _show_orders(call, db, page=page, search=search or None)


@router.message(SearchStates.waiting_query, F.text)
async def msg_search(message: Message, db: Database, state: FSMContext) -> None:
    query = (message.text or "").strip()
    if not query:
        await message.answer("Порожній запит. Спробуй ще раз.")
        return
    await state.update_data(search=query)
    await state.set_state(None)

    total = await db.count_orders_search(query)
    if total == 0:
        await message.answer(
            f"🔎 За запитом «{html.escape(query)}» нічого не знайдено.",
            reply_markup=main_menu(),
        )
        return

    rows = await db.recent_orders(limit=PAGE_SIZE, offset=0, search=query)
    pages = max(1, math.ceil(total / PAGE_SIZE))
    await message.answer(
        f"🔎 Результати за «<b>{html.escape(query)}</b>»: <b>{total}</b>",
        reply_markup=orders_keyboard(rows, 0, pages, prefix="searchpage"),
    )


async def _show_orders(
    call: CallbackQuery,
    db: Database,
    *,
    page: int,
    search: str | None = None,
) -> None:
    total = (
        await db.count_orders_search(search)
        if search
        else await db.count_orders()
    )
    pages = max(1, math.ceil(total / PAGE_SIZE))
    page = max(0, min(page, pages - 1))
    rows = await db.recent_orders(limit=PAGE_SIZE, offset=page * PAGE_SIZE, search=search)

    if not rows:
        await safe_edit(
            call,
            "📭 Поки що замовлень немає.\n\n"
            "Перевір джерела або зачекай — я надішлю, щойно щось з'явиться.",
            main_menu(),
        )
        return

    title = "🔎 Результати пошуку" if search else "📥 Останні замовлення"
    await safe_edit(
        call,
        f"{title}\n\nВсього: <b>{total}</b> · сторінка <b>{page + 1}/{pages}</b>\n"
        "Обери замовлення, щоб побачити картку:",
        orders_keyboard(rows, page, pages, prefix="searchpage" if search else "orders"),
    )


@router.callback_query(F.data.startswith("order:"))
async def cb_order(
    call: CallbackQuery,
    db: Database,
    renderer: Renderer,
    config: Settings,
) -> None:
    order_id = _to_int(call.data.split(":", 1)[1], 0)
    row = await db.get_order(order_id)
    if row is None:
        await call.answer("Замовлення не знайдено", show_alert=True)
        return
    await call.answer()
    if call.message is None:
        return
    await send_order_card(
        call.message, row, renderer, config, auto_bid=_auto_bid(row["source"], config)
    )


@router.callback_query(F.data.startswith("reply:"))
async def cb_reply(
    call: CallbackQuery,
    db: Database,
    config: Settings,
    state: FSMContext,
) -> None:
    order_id = _to_int(call.data.split(":", 1)[1], 0)
    row = await db.get_order(order_id)
    if row is None:
        await call.answer("Замовлення не знайдено", show_alert=True)
        return
    await call.answer()
    resumes = await db.library_list("resume")
    templates = await db.library_list("template")
    await state.update_data(reply_order_id=order_id)
    text = (
        "✍️ <b>Відгук на замовлення</b>\n\n"
        f"<b>{html.escape(truncate(row['title'], 140))}</b>\n\n"
        "Обери резюме або швидку відповідь. Я надішлю файл/текст сюди, "
        "а ти скопіюєш його на сайті. Або напиши власний текст."
    )
    await safe_edit(
        call,
        text,
        reply_keyboard(
            order_id,
            row["url"],
            resumes,
            templates,
            auto_bid=_auto_bid(row["source"], config),
        ),
    )


@router.callback_query(F.data.startswith("use:r:") | F.data.startswith("use:t:"))
async def cb_use_library(
    call: CallbackQuery,
    db: Database,
    config: Settings,
) -> None:
    parts = (call.data or "").split(":")
    if len(parts) != 4:
        await call.answer()
        return
    kind = "resume" if parts[1] == "r" else "template"
    item_id = _to_int(parts[2], 0)
    order_id = _to_int(parts[3], 0)

    item = await db.library_get(item_id)
    row = await db.get_order(order_id)
    if item is None or row is None or call.message is None:
        await call.answer("Не знайдено", show_alert=True)
        return
    await call.answer()
    header = f"📄 <b>{html.escape(item.title)}</b>" if kind == "resume" else f"⚡ <b>{html.escape(item.title)}</b>"
    if item.file_id:
        caption = f"{header}\n\nЗамовлення: {html.escape(truncate(row['title'], 120))}"
        await call.message.answer_document(item.file_id, caption=caption)
    elif item.text:
        body = html.escape(item.text)
        if len(body) > 3500:
            body = body[:3497] + "…"
        await call.message.answer(f"{header}\n\n<blockquote>{body}</blockquote>")

    await call.message.answer(
        "Готово. Скопіюй текст або прикріпи файл на сайті замовлення 👇",
        reply_markup=reply_result_keyboard(
            order_id,
            row["url"],
            auto_bid=_auto_bid(row["source"], config),
        ),
        disable_web_page_preview=True,
    )


@router.callback_query(F.data.startswith("custom:"))
async def cb_custom(
    call: CallbackQuery, state: FSMContext, db: Database
) -> None:
    order_id = _to_int(call.data.split(":", 1)[1], 0)
    row = await db.get_order(order_id)
    if row is None:
        await call.answer("Замовлення не знайдено", show_alert=True)
        return
    await call.answer()
    await state.set_state(ReplyStates.waiting_text)
    await state.update_data(custom_order_id=order_id)
    if call.message is not None:
        await call.message.answer(
            "✏️ Напиши текст відгуку одним повідомленням.\n\n"
            "Я поверну його готовим до копіювання разом із посиланням на замовлення.",
            reply_markup=main_menu(),
        )


@router.message(ReplyStates.waiting_text, F.text)
async def msg_custom_reply(
    message: Message,
    state: FSMContext,
    db: Database,
    config: Settings,
) -> None:
    text = (message.text or "").strip()
    if not text:
        return
    if text.startswith("/"):
        await message.answer("Скасовано.", reply_markup=main_menu())
        await state.clear()
        return

    data = await state.get_data()
    order_id = int(data.get("custom_order_id") or 0)
    row = await db.get_order(order_id)
    if row is None:
        await message.answer("Замовлення вже недоступне.", reply_markup=main_menu())
        await state.clear()
        return

    safe_text = html.escape(text)
    await message.answer(
        "✍️ <b>Готовий відгук</b>\n\n"
        f"<blockquote>{safe_text}</blockquote>\n\n"
        f'🔗 <a href="{html.escape(row["url"], quote=True)}">'
        f"{html.escape(truncate(row['title'], 100))}</a>",
        disable_web_page_preview=True,
    )
    await message.answer(
        "Скопіюй текст і встав на сторінці замовлення. "
        "Можеш зберегти цей текст як шаблон 👇",
        reply_markup=reply_result_keyboard(
            order_id,
            row["url"],
            auto_bid=_auto_bid(row["source"], config),
            can_save_template=True,
        ),
        disable_web_page_preview=True,
    )
    # Keep the text in FSM data so the "save as template" button can use it,
    # but leave the state so the next message is not treated as a reply.
    await state.set_data({"pending_text": text, "pending_order_id": order_id})
    await state.set_state(None)


@router.callback_query(F.data.startswith("savetpl:"))
async def cb_save_template(call: CallbackQuery, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    text = str(data.get("pending_text") or "").strip()
    if not text:
        await call.answer("Текст уже втрачено, напиши заново", show_alert=True)
        return
    first_line = text.splitlines()[0]
    title = truncate(first_line, 50) or "Швидка відповідь"
    await db.library_add(kind="template", title=title, text=text)
    await state.update_data(pending_text="")
    await call.answer("✅ Збережено як шаблон")
    if call.message is not None:
        await call.message.edit_reply_markup(reply_markup=None)


def _to_int(value: str, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
