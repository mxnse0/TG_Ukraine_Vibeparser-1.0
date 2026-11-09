"""Status dashboard and runtime settings."""

from __future__ import annotations

import time

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from app.bot.handlers.common import safe_edit, short_error
from app.bot.keyboards import back_to_menu, main_menu, settings_keyboard
from app.bot.states import SettingsStates
from app.config import Settings
from app.db import Database
from app.parsers import parser_meta
from app.services.renderer import Renderer, demo_order
from app.services.scheduler import Scheduler
from app.utils.time import human_time, parse_datetime, today_utc_iso

router = Router(name="settings")


@router.callback_query(F.data == "menu:status")
async def cb_status(
    call: CallbackQuery, db: Database, config: Settings, scheduler: Scheduler
) -> None:
    await call.answer()
    await safe_edit(call, await _status_text(db, config, scheduler), back_to_menu())


@router.message(Command("status"))
async def cmd_status(
    message: Message, db: Database, config: Settings, scheduler: Scheduler
) -> None:
    await message.answer(await _status_text(db, config, scheduler), reply_markup=main_menu())


@router.callback_query(F.data == "menu:settings")
async def cb_settings(call: CallbackQuery, db: Database, config: Settings) -> None:
    await call.answer()
    await safe_edit(call, await _settings_text(db, config), await _settings_keyboard(db, config))


@router.callback_query(F.data == "set:notify")
async def cb_set_notify(call: CallbackQuery, db: Database, config: Settings) -> None:
    current = await db.get_bool("notifications_enabled", True)
    await db.set_setting("notifications_enabled", not current)
    await call.answer("🔔 Сповіщення увімкнено" if not current else "🔕 Сповіщення вимкнено")
    await safe_edit(call, await _settings_text(db, config), await _settings_keyboard(db, config))


@router.callback_query(F.data == "set:interval")
async def cb_set_interval(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await state.set_state(SettingsStates.waiting_interval)
    if call.message is not None:
        await call.message.answer(
            "⏱ Вкажи інтервал перевірки в секундах (від 20 до 3600).\n\n"
            "Рекомендую 60–90 секунд: швидко й без зайвого навантаження на біржі."
        )


@router.callback_query(F.data == "set:limit")
async def cb_set_limit(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await state.set_state(SettingsStates.waiting_limit)
    if call.message is not None:
        await call.message.answer(
            "📨 Скільки карток максимум надсилати за один цикл? (1–50)\n\n"
            "Решта замовлень залишиться в «📥 Замовлення», щоб не заспамити чат."
        )


@router.callback_query(F.data == "set:mode_info")
async def cb_set_mode(call: CallbackQuery) -> None:
    await call.answer(
        "Режим картинки задається в .env: SCREENSHOT_MODE=card (швидка картка) "
        "або page (реальний скріншот сторінки через Playwright). Після зміни перезапусти бота.",
        show_alert=True,
    )


@router.callback_query(F.data == "set:test")
async def cb_set_test(
    call: CallbackQuery, renderer: Renderer, config: Settings
) -> None:
    await call.answer("Генерую тестову картку…")
    if call.message is None:
        return
    try:
        image = await renderer.render(demo_order())
        await call.message.answer_photo(
            BufferedInputFile(image, filename="vibeparser_demo.jpg"),
            caption=(
                "🧪 <b>Тестова картка</b>\n\n"
                "Так виглядатиме сповіщення про нове замовлення. "
                f"Режим: <code>{config.screenshot_mode}</code>."
            ),
        )
    except Exception:  # noqa: BLE001
        await call.message.answer("❌ Не вдалося згенерувати картку. Перевір логи.")


@router.message(SettingsStates.waiting_interval, F.text)
async def msg_interval(
    message: Message, state: FSMContext, db: Database, config: Settings
) -> None:
    try:
        value = int((message.text or "").strip())
    except ValueError:
        await message.answer("❌ Введи ціле число секунд, наприклад 75.")
        return
    if not 20 <= value <= 3600:
        await message.answer("❌ Допустимий діапазон: 20–3600 секунд.")
        return
    await db.set_setting("poll_interval", value)
    await state.clear()
    await message.answer(
        f"✅ Інтервал: <b>{value} с</b>. Новий цикл почнеться після поточного.",
        reply_markup=await _settings_keyboard(db, config),
    )


@router.message(SettingsStates.waiting_limit, F.text)
async def msg_limit(
    message: Message, state: FSMContext, db: Database, config: Settings
) -> None:
    try:
        value = int((message.text or "").strip())
    except ValueError:
        await message.answer("❌ Введи ціле число, наприклад 12.")
        return
    if not 1 <= value <= 50:
        await message.answer("❌ Допустимий діапазон: 1–50.")
        return
    await db.set_setting("notify_limit", value)
    await state.clear()
    await message.answer(
        f"✅ Ліміт сповіщень за цикл: <b>{value}</b>.",
        reply_markup=await _settings_keyboard(db, config),
    )


async def _settings_text(db: Database, config: Settings) -> str:
    notifications = await db.get_bool("notifications_enabled", True)
    interval = await db.get_int("poll_interval", config.poll_interval)
    limit = await db.get_int("notify_limit", 12)
    return (
        "⚙️ <b>Налаштування</b>\n\n"
        f"🔔 Сповіщення: <b>{'увімкнено' if notifications else 'вимкнено'}</b>\n"
        f"⏱ Інтервал: <b>{interval} с</b>\n"
        f"📨 Ліміт за цикл: <b>{limit}</b>\n"
        f"🖼 Режим картинки: <code>{config.screenshot_mode}</code>\n\n"
        "Режим картинки змінюється у <code>.env</code> "
        "(<code>SCREENSHOT_MODE=card|page</code>) і потребує перезапуску."
    )


async def _settings_keyboard(db: Database, config: Settings):
    return settings_keyboard(
        await db.get_bool("notifications_enabled", True),
        await db.get_int("poll_interval", config.poll_interval),
        await db.get_int("notify_limit", 12),
        config.screenshot_mode,
    )


async def _status_text(db: Database, config: Settings, scheduler: Scheduler) -> str:
    total = await db.count_orders()
    today = await db.count_orders_since(today_utc_iso())
    by_source = await db.count_by_source()
    states = await db.source_states()
    meta = parser_meta()
    enabled = set(await db.get_enabled_sources())
    last_poll = parse_datetime(await db.get_setting("last_poll", ""))
    last_new = await db.get_int("last_poll_new", 0)
    last_error = await db.get_setting("last_poll_error", "")
    interval = await db.get_int("poll_interval", config.poll_interval)
    resumes = len(await db.library_list("resume"))
    templates = len(await db.library_list("template"))
    uptime = _uptime(time.time() - scheduler.started_at)

    lines = [
        "📊 <b>Статус VibeParser</b>",
        "",
        f"⏱ Працюю: <b>{uptime}</b> · інтервал <b>{interval} с</b>",
        f"🗂 Замовлень у базі: <b>{total}</b> · за сьогодні: <b>{today}</b>",
        f"🆕 Останній цикл: <b>{last_new}</b> нових · {human_time(last_poll, config.tz)}",
        f"📄 Резюме: <b>{resumes}</b> · ⚡ шаблонів: <b>{templates}</b>",
        f"📡 Активних джерел: <b>{len(enabled)}</b> з {len(meta)}",
        "",
        "<b>Джерела:</b>",
    ]
    for name, info in meta.items():
        mark = "✅" if name in enabled else "⏸"
        state = states.get(name)
        count = by_source.get(name, 0)
        if state is None:
            status = "ще не перевірялося"
        elif state["last_error"]:
            status = f"⚠️ {short_error(state['last_error'], 70)}"
        else:
            status = f"OK · {state['last_count']} за цикл · {human_time(parse_datetime(state['last_ok']), config.tz)}"
        lines.append(f"{mark} <b>{info['title']}</b> — {count} всього · {status}")

    if last_error:
        lines += ["", f"⚠️ Останні помилки: {short_error(last_error, 200)}"]
    return "\n".join(lines)


def _uptime(seconds: float) -> str:
    seconds = int(max(0, seconds))
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    if days:
        return f"{days} д {hours} год"
    if hours:
        return f"{hours} год {minutes} хв"
    return f"{minutes} хв"
