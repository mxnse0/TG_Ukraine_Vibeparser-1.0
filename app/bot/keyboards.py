"""Inline keyboards used by the bot."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.models import LibraryItem

SOURCE_EMOJI = {
    "freelancehunt": "🟢",
    "weblancer": "🔵",
    "freelance_ua": "🟡",
    "freelancer": "🟠",
    "djinni": "🟣",
    "kwork": "🔴",
    "flru": "⚪",
}


def _btn(text: str, callback_data: str | None = None, url: str | None = None) -> InlineKeyboardButton:
    if url:
        return InlineKeyboardButton(text=text, url=url)
    return InlineKeyboardButton(text=text, callback_data=callback_data or "noop")


def main_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        _btn("📥 Замовлення", "orders:0"),
        _btn("🔎 Пошук", "menu:search"),
    )
    builder.row(
        _btn("📄 Резюме", "menu:resume"),
        _btn("⚡ Швидкі відповіді", "menu:templates"),
    )
    builder.row(
        _btn("🎛 Фільтри", "menu:filters"),
        _btn("📡 Джерела", "filter:src"),
    )
    builder.row(
        _btn("📊 Статус", "menu:status"),
        _btn("⚙️ Налаштування", "menu:settings"),
    )
    builder.row(_btn("🔄 Перевірити зараз", "menu:check"))
    return builder.as_markup()


def back_to_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[_btn("⬅️ Головне меню", "menu:main")]])


def order_keyboard(order_id: int, url: str, *, auto_bid: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        _btn("✍️ Відгукнутись", f"reply:{order_id}"),
        _btn("🔗 Відкрити", url=url),
    )
    if auto_bid:
        builder.row(_btn("🚀 Auto-bid на Freelancehunt", f"bid:{order_id}"))
    builder.row(_btn("📥 Усі замовлення", "orders:0"))
    return builder.as_markup()


def orders_keyboard(
    rows, page: int, pages: int, *, prefix: str = "orders"
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for row in rows:
        emoji = SOURCE_EMOJI.get(row["source"], "•")
        budget = row["budget_text"] or "без бюджету"
        title = row["title"]
        if len(title) > 38:
            title = title[:37] + "…"
        label = f"{emoji} {title} · {budget}"
        if len(label) > 62:
            label = label[:61] + "…"
        builder.row(_btn(label, f"order:{row['id']}"))

    nav = []
    if page > 0:
        nav.append(_btn("⬅️", f"{prefix}:{page - 1}"))
    nav.append(_btn(f"{page + 1}/{pages}", "noop"))
    if page + 1 < pages:
        nav.append(_btn("➡️", f"{prefix}:{page + 1}"))
    builder.row(*nav)
    builder.row(_btn("⬅️ Головне меню", "menu:main"))
    return builder.as_markup()


def reply_keyboard(
    order_id: int,
    order_url: str,
    resumes: list[LibraryItem],
    templates: list[LibraryItem],
    *,
    auto_bid: bool = False,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for item in resumes[:4]:
        prefix = "⭐ " if item.is_default else "📄 "
        builder.row(_btn(f"{prefix}{_short(item.title)}", f"use:r:{item.id}:{order_id}"))
    for item in templates[:4]:
        prefix = "⭐ " if item.is_default else "⚡ "
        builder.row(_btn(f"{prefix}{_short(item.title)}", f"use:t:{item.id}:{order_id}"))

    if not resumes:
        builder.row(_btn("➕ Додати резюме", "lib:add:resume"))
    if not templates:
        builder.row(_btn("➕ Додати швидку відповідь", "lib:add:template"))

    builder.row(_btn("✏️ Написати свій текст", f"custom:{order_id}"))
    if auto_bid:
        builder.row(_btn("🚀 Auto-bid на Freelancehunt", f"bid:{order_id}"))
    builder.row(
        _btn("🔗 Відкрити замовлення", url=order_url),
        _btn("⬅️ Назад", f"order:{order_id}"),
    )
    return builder.as_markup()


def reply_result_keyboard(
    order_id: int, url: str, *, auto_bid: bool = False, can_save_template: bool = False
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(_btn("🔗 Відкрити замовлення", url=url))
    if auto_bid:
        builder.row(_btn("🚀 Надіслати на Freelancehunt", f"bid:{order_id}"))
    if can_save_template:
        builder.row(_btn("💾 Зберегти як шаблон", f"savetpl:{order_id}"))
    builder.row(_btn("⬅️ До замовлення", f"order:{order_id}"))
    return builder.as_markup()


def library_list_keyboard(kind: str, items: list[LibraryItem]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for item in items:
        prefix = "⭐ " if item.is_default else ("📄 " if kind == "resume" else "⚡ ")
        builder.row(_btn(f"{prefix}{_short(item.title, 44)}", f"lib:view:{item.id}"))
    builder.row(
        _btn("📎 Додати файлом", f"lib:file:{kind}"),
        _btn("⌨️ Додати текстом", f"lib:text:{kind}"),
    )
    builder.row(_btn("⬅️ Головне меню", "menu:main"))
    return builder.as_markup()


def library_item_keyboard(item: LibraryItem) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if not item.is_default:
        builder.row(_btn("⭐ Зробити за замовчуванням", f"lib:def:{item.id}"))
    builder.row(_btn("🗑 Видалити", f"lib:del:{item.id}"))
    builder.row(_btn("⬅️ Назад", f"menu:{'resume' if item.kind == 'resume' else 'templates'}"))
    return builder.as_markup()


def filters_keyboard(
    min_budget: float, max_budget: float, skip_no_budget: bool
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        _btn("🔑 Ключові слова", "filter:kw"),
        _btn("🚫 Мінус-слова", "filter:ex"),
    )
    builder.row(_btn("💰 Бюджет", "filter:budget"))
    builder.row(
        _btn(
            f"Без бюджету: {'пропускати' if skip_no_budget else 'приймати'}",
            "filter:skip",
        )
    )
    builder.row(_btn("📡 Джерела", "filter:src"))
    builder.row(_btn("🧹 Скинути фільтри", "filter:reset"))
    builder.row(_btn("⬅️ Головне меню", "menu:main"))
    return builder.as_markup()


def sources_keyboard(enabled: set[str], meta: dict[str, dict[str, object]]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for name, info in meta.items():
        mark = "✅" if name in enabled else "⬜"
        builder.row(_btn(f"{mark} {info['title']}", f"filter:src:{name}"))
    builder.row(_btn("⬅️ Фільтри", "menu:filters"))
    return builder.as_markup()


def settings_keyboard(
    notifications: bool, interval: int, limit: int, mode: str
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        _btn(f"🔔 Сповіщення: {'увімк' if notifications else 'вимк'}", "set:notify")
    )
    builder.row(_btn(f"⏱ Інтервал: {interval} с", "set:interval"))
    builder.row(_btn(f"📨 Ліміт за цикл: {limit}", "set:limit"))
    builder.row(_btn(f"🖼 Картинка: {mode}", "set:mode_info"))
    builder.row(_btn("🧪 Тестова картка", "set:test"))
    builder.row(_btn("⬅️ Головне меню", "menu:main"))
    return builder.as_markup()


def bid_confirm_keyboard(order_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        _btn("✅ Надіслати", f"bid:confirm:{order_id}"),
        _btn("❌ Скасувати", "bid:cancel"),
    )
    return builder.as_markup()


def search_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[_btn("⬅️ Скасувати", "menu:main")]]
    )


def _short(value: str, limit: int = 34) -> str:
    value = (value or "").strip()
    return value if len(value) <= limit else value[: limit - 1] + "…"
