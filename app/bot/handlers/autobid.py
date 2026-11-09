"""Direct bidding on Freelancehunt through its official API."""

from __future__ import annotations

import html
import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards import bid_confirm_keyboard, main_menu
from app.bot.states import AutoBidStates
from app.config import Settings
from app.db import Database
from app.services.freelancehunt_bid import BidError, place_bid
from app.utils.text import truncate

log = logging.getLogger(__name__)
router = Router(name="autobid")


@router.callback_query(
    F.data.startswith("bid:")
    & ~F.data.startswith("bid:confirm:")
    & ~F.data.startswith("bid:cancel")
)
async def cb_bid_start(
    call: CallbackQuery, state: FSMContext, db: Database, config: Settings
) -> None:
    if not config.freelancehunt_token:
        await call.answer(
            "Auto-bid потребує FREELANCEHUNT_TOKEN у .env. "
            "Додай токен і перезапусти бота.",
            show_alert=True,
        )
        return

    order_id = _to_int((call.data or "0").split(":")[1])
    row = await db.get_order(order_id)
    if row is None:
        await call.answer("Замовлення не знайдено", show_alert=True)
        return
    if row["source"] != "freelancehunt":
        await call.answer("Auto-bid доступний лише для Freelancehunt", show_alert=True)
        return

    data = await state.get_data()
    pending = str(data.get("pending_text") or "").strip()
    await state.set_state(AutoBidStates.comment)
    await state.update_data(bid_order_id=order_id)

    if pending:
        await state.update_data(bid_comment=pending)
        await state.set_state(AutoBidStates.amount)
        if call.message is not None:
            await call.message.answer(
                "🚀 <b>Auto-bid Freelancehunt</b>\n\n"
                f"Текст відгуку взято з твого повідомлення:\n"
                f"<blockquote>{html.escape(truncate(pending, 300))}</blockquote>\n\n"
                f"Вкажи суму в <b>{html.escape(row['currency'] or 'UAH')}</b> "
                "(тільки число)."
            )
        return

    if call.message is not None:
        await call.message.answer(
            "🚀 <b>Auto-bid Freelancehunt</b>\n\n"
            f"Замовлення: <b>{html.escape(truncate(row['title'], 140))}</b>\n"
            f"Бюджет: {html.escape(row['budget_text'] or 'не вказано')}\n\n"
            "Надішли текст відгуку (comment) одним повідомленням."
        )


@router.message(AutoBidStates.comment, F.text)
async def msg_bid_comment(
    message: Message, state: FSMContext, db: Database
) -> None:
    text = (message.text or "").strip()
    if not text:
        return
    data = await state.get_data()
    row = await db.get_order(int(data.get("bid_order_id") or 0))
    if row is None:
        await state.clear()
        await message.answer("Замовлення недоступне.", reply_markup=main_menu())
        return
    await state.update_data(bid_comment=text)
    await state.set_state(AutoBidStates.amount)
    currency = row["currency"] or "UAH"
    hint = row["budget_text"] or "без орієнтира"
    await message.answer(
        f"💰 Вкажи суму в <b>{html.escape(currency)}</b> (тільки число).\n"
        f"Орієнтир: {html.escape(hint)}"
    )


@router.message(AutoBidStates.amount, F.text)
async def msg_bid_amount(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").replace(" ", "").replace(",", ".").strip()
    try:
        amount = float(raw)
    except ValueError:
        await message.answer("❌ Введи суму числом, наприклад 2500.")
        return
    if amount <= 0:
        await message.answer("❌ Сума має бути більшою за 0.")
        return
    await state.update_data(bid_amount=amount)
    await state.set_state(AutoBidStates.days)
    await message.answer("🕒 За скільки днів виконаєш? Введи ціле число днів.")


@router.message(AutoBidStates.days, F.text)
async def msg_bid_days(
    message: Message, state: FSMContext, db: Database, config: Settings
) -> None:
    try:
        days = int((message.text or "").strip())
    except ValueError:
        await message.answer("❌ Введи ціле число днів, наприклад 5.")
        return
    if not 1 <= days <= 365:
        await message.answer("❌ Допустимо від 1 до 365 днів.")
        return
    await state.update_data(bid_days=days)
    data = await state.get_data()
    row = await db.get_order(int(data.get("bid_order_id") or 0))
    if row is None:
        await state.clear()
        await message.answer("Замовлення недоступне.", reply_markup=main_menu())
        return

    comment = str(data.get("bid_comment") or "")
    amount = float(data.get("bid_amount") or 0)
    currency = row["currency"] or "UAH"
    await message.answer(
        "🚀 <b>Перевір відгук перед відправкою</b>\n\n"
        f"<b>Замовлення:</b> {html.escape(truncate(row['title'], 120))}\n"
        f"<b>Сума:</b> {amount:g} {html.escape(currency)}\n"
        f"<b>Термін:</b> {days} дн.\n\n"
        f"<b>Коментар:</b>\n<blockquote>{html.escape(truncate(comment, 500))}</blockquote>\n\n"
        "Натисни «✅ Надіслати», щоб опублікувати відгук на Freelancehunt.",
        reply_markup=bid_confirm_keyboard(int(row["id"])),
    )


@router.callback_query(F.data.startswith("bid:confirm:"))
async def cb_bid_confirm(
    call: CallbackQuery, state: FSMContext, db: Database, config: Settings
) -> None:
    data = await state.get_data()
    order_id = _to_int((call.data or "0").split(":")[2])
    row = await db.get_order(order_id)
    if row is None or int(data.get("bid_order_id") or 0) != order_id:
        await call.answer("Сесія втрачена, почни заново", show_alert=True)
        await state.clear()
        return

    comment = str(data.get("bid_comment") or "")
    amount = float(data.get("bid_amount") or 0)
    days = int(data.get("bid_days") or 0)
    currency = row["currency"] or "UAH"

    await call.answer("Надсилаю…")
    try:
        message = await place_bid(
            token=config.freelancehunt_token,
            project_id=row["external_id"],
            comment=comment,
            amount=amount,
            currency=currency,
            days=days,
        )
    except BidError as exc:
        if call.message is not None:
            await call.message.answer(f"❌ <b>Не вдалося надіслати</b>\n\n{html.escape(str(exc))}")
        return
    except Exception as exc:  # noqa: BLE001
        log.exception("Bid request failed")
        if call.message is not None:
            await call.message.answer(f"❌ Помилка запиту: {html.escape(str(exc))}")
        return

    await state.clear()
    if call.message is not None:
        await call.message.answer(
            f"✅ <b>{html.escape(message)}</b>\n\n"
            f"Замовлення: {html.escape(truncate(row['title'], 120))}"
        )


@router.callback_query(F.data == "bid:cancel")
async def cb_bid_cancel(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await call.answer("Скасовано")
    if call.message is not None:
        await call.message.edit_reply_markup(reply_markup=None)


def _to_int(value: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
