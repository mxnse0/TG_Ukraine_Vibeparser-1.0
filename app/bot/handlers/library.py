"""Saved resumes and quick-reply templates."""

from __future__ import annotations

import html
import logging
from pathlib import Path
from uuid import uuid4

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.handlers.common import safe_edit
from app.bot.keyboards import library_item_keyboard, library_list_keyboard
from app.bot.states import LibraryStates
from app.config import Settings
from app.db import Database
from app.utils.text import truncate

log = logging.getLogger(__name__)
router = Router(name="library")

KIND_TITLES = {"resume": "📄 Резюме", "template": "⚡ Швидкі відповіді"}
MAX_FILE_SIZE = 20 * 1024 * 1024


@router.callback_query(F.data.in_({"menu:resume", "menu:templates"}))
async def cb_library(call: CallbackQuery, db: Database) -> None:
    await call.answer()
    kind = "resume" if call.data == "menu:resume" else "template"
    await _show_library(call, db, kind)


@router.callback_query(F.data.startswith("lib:list:"))
async def cb_library_list(call: CallbackQuery, db: Database) -> None:
    await call.answer()
    kind = _kind_from(call.data.split(":")[-1])
    await _show_library(call, db, kind)


@router.callback_query(F.data.startswith("lib:add:"))
async def cb_library_add(call: CallbackQuery, db: Database) -> None:
    await call.answer()
    kind = _kind_from(call.data.split(":")[-1])
    await _show_library(call, db, kind)


@router.callback_query(F.data.startswith("lib:file:"))
async def cb_library_file(
    call: CallbackQuery, state: FSMContext, db: Database
) -> None:
    await call.answer()
    kind = _kind_from(call.data.split(":")[-1])
    await state.set_state(LibraryStates.waiting_file)
    await state.update_data(lib_kind=kind)
    if call.message is not None:
        await call.message.answer(
            f"📎 Надішли файл для «{KIND_TITLES[kind]}».\n\n"
            "Підійде PDF, DOC, DOCX, TXT, RTF або ODT (до 20 МБ). "
            "Назва файлу стане назвою картки.",
            reply_markup=library_list_keyboard(kind, await db.library_list(kind)),
        )


@router.callback_query(F.data.startswith("lib:text:"))
async def cb_library_text(
    call: CallbackQuery, state: FSMContext, db: Database
) -> None:
    await call.answer()
    kind = _kind_from(call.data.split(":")[-1])
    await state.set_state(LibraryStates.waiting_text)
    await state.update_data(lib_kind=kind)
    if call.message is not None:
        await call.message.answer(
            f"⌨️ Надішли текст для «{KIND_TITLES[kind]}» одним повідомленням.\n\n"
            "Перший рядок стане назвою. Потім цей текст можна буде швидко "
            "відправити собі під час відгуку.",
            reply_markup=library_list_keyboard(kind, await db.library_list(kind)),
        )


@router.message(LibraryStates.waiting_file, F.document)
async def msg_library_file(
    message: Message, state: FSMContext, db: Database, config: Settings
) -> None:
    document = message.document
    if document is None:
        return
    data = await state.get_data()
    kind = _kind_from(str(data.get("lib_kind") or "resume"))

    if document.file_size and document.file_size > MAX_FILE_SIZE:
        await message.answer("❌ Файл більший за 20 МБ. Стисни його або надішли текст.")
        return

    file_name = document.file_name or f"{kind}_{document.file_unique_id}"
    safe_name = f"{uuid4().hex[:10]}_{Path(file_name).name}"
    safe_name = "".join(ch for ch in safe_name if ch.isalnum() or ch in "._- ")
    target = config.data_dir / "resumes" / safe_name
    try:
        await message.bot.download(document, destination=str(target))
    except Exception:  # noqa: BLE001
        log.exception("Failed to download document")
        await message.answer("❌ Не вдалося завантажити файл. Спробуй ще раз.")
        return

    title = Path(file_name).stem or "Без назви"
    await db.library_add(
        kind=kind,
        title=truncate(title, 60),
        file_id=document.file_id,
        file_name=file_name,
        mime_type=document.mime_type,
        local_path=str(target),
    )
    await state.clear()
    items = await db.library_list(kind)
    await message.answer(
        f"✅ Додано до «{KIND_TITLES[kind]}»: <b>{html.escape(title)}</b>",
        reply_markup=library_list_keyboard(kind, items),
    )


@router.message(LibraryStates.waiting_file)
async def msg_library_file_wrong(message: Message) -> None:
    await message.answer("📎 Надішли саме файл (document), будь ласка.")


@router.message(LibraryStates.waiting_text, F.text)
async def msg_library_text(
    message: Message, state: FSMContext, db: Database
) -> None:
    text = (message.text or "").strip()
    if not text:
        return
    if text.startswith("/"):
        await state.clear()
        await message.answer("Скасовано.")
        return

    data = await state.get_data()
    kind = _kind_from(str(data.get("lib_kind") or "resume"))
    first_line = text.splitlines()[0]
    title = truncate(first_line, 60) or "Без назви"
    await db.library_add(kind=kind, title=title, text=text)
    await state.clear()
    items = await db.library_list(kind)
    await message.answer(
        f"✅ Додано до «{KIND_TITLES[kind]}»: <b>{html.escape(title)}</b>",
        reply_markup=library_list_keyboard(kind, items),
    )


@router.callback_query(F.data.startswith("lib:view:"))
async def cb_library_view(call: CallbackQuery, db: Database) -> None:
    await call.answer()
    item_id = _to_int(call.data.split(":")[-1])
    item = await db.library_get(item_id)
    if item is None or call.message is None:
        await call.answer("Не знайдено", show_alert=True)
        return

    title = f"📄 <b>{html.escape(item.title)}</b>"
    if item.is_default:
        title += " ⭐"
    if item.file_id:
        await call.message.answer_document(
            item.file_id,
            caption=f"{title}\n\nФайл: {html.escape(item.file_name or '—')}",
        )
    elif item.text:
        body = html.escape(item.text)
        if len(body) > 3500:
            body = body[:3497] + "…"
        await call.message.answer(f"{title}\n\n<blockquote>{body}</blockquote>")
    else:
        await call.message.answer(f"{title}\n\nПорожній елемент.")

    await call.message.answer(
        "Дії з елементом:",
        reply_markup=library_item_keyboard(item),
    )


@router.callback_query(F.data.startswith("lib:def:"))
async def cb_library_default(call: CallbackQuery, db: Database) -> None:
    item_id = _to_int(call.data.split(":")[-1])
    item = await db.library_get(item_id)
    if item is None:
        await call.answer("Не знайдено", show_alert=True)
        return
    await db.library_set_default(item_id)
    await call.answer("⭐ Тепер за замовчуванням")
    await _show_library(call, db, item.kind)


@router.callback_query(F.data.startswith("lib:del:"))
async def cb_library_delete(call: CallbackQuery, db: Database) -> None:
    item_id = _to_int(call.data.split(":")[-1])
    item = await db.library_delete(item_id)
    if item is None:
        await call.answer("Не знайдено", show_alert=True)
        return
    if item.local_path:
        try:
            Path(item.local_path).unlink(missing_ok=True)
        except OSError:
            log.warning("Could not remove local file %s", item.local_path)
    await call.answer("🗑 Видалено")
    await _show_library(call, db, item.kind)


async def _show_library(call: CallbackQuery, db: Database, kind: str) -> None:
    items = await db.library_list(kind)
    if items:
        lines = [f"<b>{KIND_TITLES[kind]}</b>", "", f"Збережено: <b>{len(items)}</b>", ""]
        for item in items[:10]:
            mark = " ⭐" if item.is_default else ""
            icon = "📎" if item.file_id else "⌨️"
            lines.append(f"{icon} {html.escape(item.title)}{mark}")
        lines += ["", "Обери елемент, щоб переглянути або змінити."]
    else:
        lines = [
            f"<b>{KIND_TITLES[kind]}</b>",
            "",
            "Тут поки порожньо.",
            "Додай файл або текст — і я зможу швидко надсилати його під час відгуку.",
        ]
    await safe_edit(call, "\n".join(lines), library_list_keyboard(kind, items))


def _kind_from(value: str) -> str:
    return value if value in {"resume", "template"} else "resume"


def _to_int(value: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
