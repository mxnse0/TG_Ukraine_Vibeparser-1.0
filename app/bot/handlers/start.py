"""Start, help, main menu and manual poll."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.handlers.common import safe_edit, short_error
from app.bot.keyboards import back_to_menu, main_menu, search_keyboard
from app.bot.states import SearchStates
from app.config import Settings
from app.db import Database
from app.services.collector import Collector

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message, db: Database, config: Settings) -> None:
    if not config.admin_id_list and message.from_user:
        owner = await db.get_setting("owner_id", "")
        if not owner:
            await db.set_setting("owner_id", message.from_user.id)

    enabled = await db.get_enabled_sources()
    interval = await db.get_int("poll_interval", config.poll_interval)
    text = (
        "🤖 <b>VibeParser</b> — твій мисливець за замовленнями.\n\n"
        f"Я перевіряю <b>{len(enabled)}</b> джерел кожні <b>{interval}</b> секунд, "
        "фільтрую за твоїми ключовими словами та бюджетом і надсилаю картку "
        "з кнопкою швидкого відгуку.\n\n"
        "Що вмію:\n"
        "• 📥 показувати останні замовлення та шукати по них;\n"
        "• 📄 зберігати резюме файлом або текстом;\n"
        "• ⚡ зберігати швидкі відповіді та шаблони;\n"
        "• ✍️ готувати відгук із твоїм текстом, файлом або шаблоном;\n"
        "• 🚀 надсилати відгук на Freelancehunt через офіційний API "
        "(якщо доданий токен);\n"
        "• 🎛 фільтрувати за словами, мінус-словами та бюджетом.\n\n"
        "Обери дію нижче 👇"
    )
    await message.answer(text, reply_markup=main_menu())


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    text = (
        "<b>Як користуватися</b>\n\n"
        "<b>1. Сповіщення.</b> Коли на одному з джерел з'являється нове замовлення, "
        "бот надсилає картку з описом, бюджетом і QR-кодом. Кнопка «✍️ Відгукнутись» "
        "відкриває вибір резюме / швидкої відповіді / власного тексту.\n\n"
        "<b>2. Резюме.</b> Меню «📄 Резюме» → додай PDF/DOCX файлом або встав текст. "
        "Один документ можна позначити як типовий.\n\n"
        "<b>3. Швидкі відповіді.</b> Меню «⚡ Швидкі відповіді» → збережи текст або "
        "файл. Під час відгуку бот надішле його тобі разом із посиланням на замовлення, "
        "щоб ти міг скопіювати / прикріпити на сайті.\n\n"
        "<b>4. Auto-bid.</b> Для Freelancehunt можна надіслати відгук напряму: "
        "додай <code>FREELANCEHUNT_TOKEN</code> у <code>.env</code>, натисни "
        "«🚀 Auto-bid», вкажи текст, суму та термін. Для інших бірж бот готує "
        "готовий текст і відкриває сторінку замовлення — автоматично писати туди "
        "неможливо без їхнього API.\n\n"
        "<b>5. Фільтри.</b> «🎛 Фільтри» → ключові слова, мінус-слова, бюджет у гривнях "
        "(інші валюти конвертуються за курсом із .env).\n\n"
        "<b>Команди:</b> /start, /menu, /check, /help\n\n"
        "⚠️ Бот приватний: доступ має лише власник із <code>ADMIN_IDS</code>."
    )
    await message.answer(text, reply_markup=main_menu())


@router.message(Command("menu"))
async def cmd_menu(message: Message) -> None:
    await message.answer("Головне меню 👇", reply_markup=main_menu())


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Скасовано.", reply_markup=main_menu())


@router.message(Command("check"))
async def cmd_check(message: Message, collector: Collector) -> None:
    status = await message.answer("⏳ Перевіряю джерела…")
    result = await collector.collect_once()
    if result.busy:
        await status.edit_text("⏳ Перевірка вже виконується. Спробуй за хвилину.")
        return
    await status.edit_text(_poll_text(result), reply_markup=back_to_menu())


@router.callback_query(F.data == "menu:main")
async def cb_menu(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await call.answer()
    await safe_edit(
        call,
        "Головне меню 👇\n\nОбери розділ:",
        main_menu(),
    )


@router.callback_query(F.data == "menu:help")
async def cb_help(call: CallbackQuery) -> None:
    await call.answer()
    await safe_edit(
        call,
        "<b>Довідка</b>\n\n"
        "• 📥 Замовлення — останні знайдені замовлення.\n"
        "• ✍️ Відгукнутись — вибрати резюме, шаблон або свій текст.\n"
        "• 📄 Резюме / ⚡ Швидкі відповіді — твоя бібліотека.\n"
        "• 🎛 Фільтри — слова та бюджет.\n"
        "• 📡 Джерела — які сайти перевіряти.\n"
        "• 📊 Статус — здоров'я джерел і статистика.\n"
        "• ⚙️ Налаштування — інтервал, ліміт, тест картки.\n\n"
        "Команди: /start /menu /check /help",
        main_menu(),
    )


@router.callback_query(F.data == "menu:check")
async def cb_check(call: CallbackQuery, collector: Collector) -> None:
    result = await collector.collect_once()
    if result.busy:
        await call.answer("Перевірка вже виконується, зачекай", show_alert=True)
        return
    await call.answer("Готово")
    if call.message is not None:
        await call.message.answer(_poll_text(result), reply_markup=back_to_menu())


@router.callback_query(F.data == "menu:search")
async def cb_search(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await state.set_state(SearchStates.waiting_query)
    if call.message is not None:
        await call.message.answer(
            "🔎 Напиши слово або фразу для пошуку серед збережених замовлень:",
            reply_markup=search_keyboard(),
        )


@router.callback_query(F.data == "noop")
async def cb_noop(call: CallbackQuery) -> None:
    await call.answer()


def _poll_text(result) -> str:
    lines = [
        "✅ <b>Перевірку завершено</b>",
        "",
        f"Отримано: <b>{result.fetched}</b>",
        f"Нових: <b>{result.new}</b>",
        f"Підійшло під фільтри: <b>{result.matched}</b>",
        f"Надіслано: <b>{result.notified}</b>",
        f"Час: <b>{result.duration:.1f} с</b>",
    ]
    if result.skipped:
        lines.append(f"Пропущено через ліміт: <b>{result.skipped}</b>")
    if result.errors:
        lines += ["", "⚠️ <b>Помилки джерел:</b>"]
        for source, error in result.errors.items():
            lines.append(f"• <code>{source}</code>: {short_error(error, 90)}")
    return "\n".join(lines)
