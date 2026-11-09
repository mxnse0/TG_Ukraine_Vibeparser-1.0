"""Keyword, budget and source filters."""

from __future__ import annotations

import html
import re

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.handlers.common import safe_edit
from app.bot.keyboards import filters_keyboard, sources_keyboard
from app.bot.states import FilterStates
from app.db import Database
from app.parsers import DEFAULT_SOURCES, parser_meta
from app.utils.text import split_terms

router = Router(name="filters")


@router.callback_query(F.data == "menu:filters")
async def cb_filters(call: CallbackQuery, db: Database) -> None:
    await call.answer()
    await _show_filters(call, db)


@router.callback_query(F.data == "filter:kw")
async def cb_filter_keywords(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await state.set_state(FilterStates.waiting_keywords)
    if call.message is not None:
        await call.message.answer(
            "🔑 Надішли ключові слова через кому або з нового рядка.\n\n"
            "Наприклад: <code>python, telegram bot, парсинг, aiogram</code>\n"
            "Замовлення має містити хоча б одне з них. Щоб очистити — надішли <code>-</code>."
        )


@router.callback_query(F.data == "filter:ex")
async def cb_filter_exclude(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await state.set_state(FilterStates.waiting_exclude)
    if call.message is not None:
        await call.message.answer(
            "🚫 Надішли мінус-слова через кому.\n\n"
            "Якщо замовлення містить хоча б одне з них, я його пропущу. "
            "Наприклад: <code>1с, бухгалтер, росія, без оплати</code>\n"
            "Щоб очистити — надішли <code>-</code>."
        )


@router.callback_query(F.data == "filter:budget")
async def cb_filter_budget(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await state.set_state(FilterStates.waiting_budget)
    if call.message is not None:
        await call.message.answer(
            "💰 Вкажи мінімальний і максимальний бюджет у гривнях через пробіл.\n\n"
            "Наприклад: <code>1000 15000</code>\n"
            "Тільки мінімум: <code>2000 0</code>\n"
            "Вимкнути обмеження: <code>0 0</code>\n\n"
            "Бюджети в інших валютах конвертуються за курсом із .env."
        )


@router.callback_query(F.data == "filter:skip")
async def cb_filter_skip(call: CallbackQuery, db: Database) -> None:
    current = await db.get_bool("skip_no_budget", False)
    await db.set_setting("skip_no_budget", not current)
    await call.answer("✅ Пропускати замовлення без бюджету" if not current else "✅ Приймати без бюджету")
    await _show_filters(call, db)


@router.callback_query(F.data == "filter:src")
async def cb_filter_sources(call: CallbackQuery, db: Database) -> None:
    await call.answer()
    enabled = set(await db.get_enabled_sources())
    await safe_edit(
        call,
        "📡 <b>Джерела</b>\n\n"
        "Натискай, щоб увімкнути або вимкнути. Має бути активним хоча б одне.\n\n"
        "🟢 Freelancehunt, 🔵 Weblancer, 🟡 Freelance.ua та 🟠 Freelancer.com "
        "перевірені й працюють. 🟣 Djinni, 🔴 Kwork і ⚪ FL.ru — опційні: "
        "можуть бути недоступні з твоєї мережі.",
        sources_keyboard(enabled, parser_meta()),
    )


@router.callback_query(F.data.startswith("filter:src:"))
async def cb_filter_source_toggle(call: CallbackQuery, db: Database) -> None:
    name = (call.data or "").split(":", 2)[2]
    meta = parser_meta()
    if name not in meta:
        await call.answer("Невідоме джерело", show_alert=True)
        return
    enabled = set(await db.get_enabled_sources())
    if name in enabled:
        if len(enabled) == 1:
            await call.answer("Має залишитися хоча б одне джерело", show_alert=True)
            return
        enabled.remove(name)
    else:
        enabled.add(name)
    # Preserve the canonical order.
    ordered = [source for source in meta if source in enabled]
    await db.set_setting("enabled_sources", ",".join(ordered))
    await call.answer("Увімкнено" if name in enabled else "Вимкнено")
    await safe_edit(
        call,
        "📡 <b>Джерела</b>\n\n"
        f"Активних: <b>{len(ordered)}</b> з {len(meta)}.\n"
        "Натискай, щоб перемкнути:",
        sources_keyboard(set(ordered), meta),
    )


@router.callback_query(F.data == "filter:reset")
async def cb_filter_reset(call: CallbackQuery, db: Database) -> None:
    await db.set_setting("keywords", "")
    await db.set_setting("exclude_keywords", "")
    await db.set_setting("min_budget", "0")
    await db.set_setting("max_budget", "0")
    await db.set_setting("skip_no_budget", "0")
    await db.set_setting("enabled_sources", ",".join(DEFAULT_SOURCES))
    await call.answer("🧹 Фільтри скинуто")
    await _show_filters(call, db)


@router.message(FilterStates.waiting_keywords, F.text)
async def msg_filter_keywords(
    message: Message, state: FSMContext, db: Database
) -> None:
    value = _clean_terms_input(message.text)
    await db.set_setting("keywords", value)
    await state.clear()
    await message.answer(
        "✅ Ключові слова оновлено."
        if value
        else "✅ Ключові слова очищено — надсилатиму всі замовлення.",
    )
    await _send_filters(message, db)


@router.message(FilterStates.waiting_exclude, F.text)
async def msg_filter_exclude(
    message: Message, state: FSMContext, db: Database
) -> None:
    value = _clean_terms_input(message.text)
    await db.set_setting("exclude_keywords", value)
    await state.clear()
    await message.answer("✅ Мінус-слова оновлено." if value else "✅ Мінус-слова очищено.")
    await _send_filters(message, db)


@router.message(FilterStates.waiting_budget, F.text)
async def msg_filter_budget(
    message: Message, state: FSMContext, db: Database
) -> None:
    raw = message.text or ""
    numbers = re.findall(
        r"\d{1,3}(?:[ \u00a0]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?", raw
    )
    if not numbers:
        await message.answer("❌ Не бачу чисел. Приклад: <code>1000 15000</code>")
        return
    values = [
        float(value.replace(" ", "").replace("\u00a0", "").replace(",", "."))
        for value in numbers[:2]
    ]
    min_budget = values[0] if values else 0.0
    max_budget = values[1] if len(values) > 1 else 0.0
    if max_budget and min_budget > max_budget:
        await message.answer("❌ Мінімум більший за максимум. Спробуй ще раз.")
        return
    await db.set_setting("min_budget", str(min_budget))
    await db.set_setting("max_budget", str(max_budget))
    await state.clear()
    if min_budget == 0 and max_budget == 0:
        await message.answer("✅ Обмеження за бюджетом вимкнено.")
    else:
        await message.answer("✅ Бюджетний фільтр оновлено.")
    await _send_filters(message, db)


async def _show_filters(call: CallbackQuery, db: Database) -> None:
    text, keyboard = await _filters_view(db)
    await safe_edit(call, text, keyboard)


async def _send_filters(message: Message, db: Database) -> None:
    text, keyboard = await _filters_view(db)
    await message.answer(text, reply_markup=keyboard)


async def _filters_view(db: Database):
    keywords = await db.get_setting("keywords", "")
    exclude = await db.get_setting("exclude_keywords", "")
    min_budget = await db.get_float("min_budget", 0)
    max_budget = await db.get_float("max_budget", 0)
    skip_no_budget = await db.get_bool("skip_no_budget", False)
    enabled = await db.get_enabled_sources()

    if min_budget and max_budget:
        budget = f"{min_budget:g} – {max_budget:g} UAH"
    elif min_budget:
        budget = f"від {min_budget:g} UAH"
    elif max_budget:
        budget = f"до {max_budget:g} UAH"
    else:
        budget = "без обмежень"

    text = (
        "🎛 <b>Фільтри</b>\n\n"
        f"🔑 <b>Ключові слова:</b> {_fmt_terms(keywords) or 'не задано (усі)'}\n"
        f"🚫 <b>Мінус-слова:</b> {_fmt_terms(exclude) or 'не задано'}\n"
        f"💰 <b>Бюджет:</b> {budget}\n"
        f"📄 <b>Без бюджету:</b> {'пропускати' if skip_no_budget else 'приймати'}\n"
        f"📡 <b>Джерела:</b> {len(enabled)} активних\n\n"
        "Фільтр за словами перевіряє назву, опис, категорію та теги."
    )
    return text, filters_keyboard(min_budget, max_budget, skip_no_budget)


def _clean_terms_input(value: str | None) -> str:
    raw = (value or "").strip()
    if raw in {"-", "—", "0"}:
        return ""
    terms = split_terms(raw)
    return ", ".join(dict.fromkeys(terms))


def _fmt_terms(value: str) -> str:
    terms = [term.strip() for term in value.split(",") if term.strip()]
    if not terms:
        return ""
    return html.escape(", ".join(terms[:8])) + ("…" if len(terms) > 8 else "")
