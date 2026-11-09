"""Router registration."""

from aiogram import Dispatcher

from app.bot.handlers import autobid, filters, library, orders, settings, start


def setup_routers(dp: Dispatcher) -> None:
    # Order matters: command/menu handlers first, state handlers after them.
    dp.include_router(start.router)
    dp.include_router(library.router)
    dp.include_router(filters.router)
    dp.include_router(orders.router)
    dp.include_router(autobid.router)
    dp.include_router(settings.router)
