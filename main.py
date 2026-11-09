"""VibeParser entry point: Telegram bot + background poller."""

from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
import sys
import traceback
from logging.handlers import RotatingFileHandler

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramConflictError, TelegramUnauthorizedError
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, ErrorEvent
from pydantic import ValidationError

from app.bot.handlers import setup_routers
from app.bot.middlewares import AccessMiddleware
from app.config import Settings
from app.db import Database
from app.paths import BASE_DIR, RESOURCE_DIR, is_frozen
from app.services.collector import Collector
from app.services.notifier import Notifier
from app.services.renderer import Renderer
from app.services.scheduler import Scheduler
from app.utils.single_instance import SingleInstance

log = logging.getLogger("vibeparser")

EXIT_OK = 0
EXIT_CONFIG = 2
EXIT_ALREADY_RUNNING = 3

CLI_COMMANDS = {"sources", "poll", "demo", "status"}


def _configure_stdio() -> None:
    """Make Ukrainian text readable in the Windows console."""
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass


def _pause() -> None:
    """Keep a double-clicked console window open so the message is readable."""
    if not is_frozen():
        return
    try:
        input("\nНатисни Enter, щоб закрити…")
    except (EOFError, KeyboardInterrupt):
        pass


def _offer_env_edit() -> None:
    if not is_frozen():
        return
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return
    try:
        answer = input("Відкрити .env у Notepad зараз? [y/N] ").strip().casefold()
    except (EOFError, KeyboardInterrupt):
        return
    if answer in {"y", "yes", "т", "так"}:
        try:
            subprocess.Popen(["notepad.exe", str(env_path)])
        except OSError:
            pass


def _ensure_env_file() -> bool:
    """Create .env from the bundled template on the very first run."""
    env_path = BASE_DIR / ".env"
    if env_path.exists():
        return False
    template = RESOURCE_DIR / ".env.example"
    if not template.exists():
        return False
    try:
        shutil.copyfile(template, env_path)
    except OSError:
        print(f"⚠️ Не вдалося створити {env_path}")
        return False
    return True


def setup_logging(config: Settings) -> None:
    config.ensure_dirs()
    level = getattr(logging, config.log_level.upper(), logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s", "%Y-%m-%d %H:%M:%S"
    )
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    root.addHandler(console)

    file_handler = RotatingFileHandler(
        config.data_dir / "vibeparser.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)


async def run() -> int:
    created_env = _ensure_env_file()
    config = Settings()
    setup_logging(config)

    if created_env:
        print(f"📝 Створено файл налаштувань: {BASE_DIR / '.env'}")
        log.info("Created default .env at %s", BASE_DIR / ".env")

    if not config.has_valid_bot_token:
        log.error("BOT_TOKEN is missing or still the example value")
        print(
            "\n❌ BOT_TOKEN не налаштований (порожній або з прикладу).\n\n"
            f"1. Відкрий файл: {BASE_DIR / '.env'}\n"
            "2. Встав справжній токен від @BotFather у рядок BOT_TOKEN=...\n"
            "3. Запусти VibeParser знову.\n"
        )
        return EXIT_CONFIG

    instance = SingleInstance(config.data_dir / "vibeparser.lock")
    if not instance.acquire():
        log.error("Another VibeParser instance is already running")
        print(
            "\n⚠️ VibeParser вже запущено в іншому вікні.\n"
            "Закрий попередній процес і запусти цей файл ще раз.\n"
        )
        return EXIT_ALREADY_RUNNING

    db = Database(config.db_path)
    renderer: Renderer | None = None
    collector: Collector | None = None
    scheduler: Scheduler | None = None
    bot: Bot | None = None

    try:
        await db.connect()
        await db.init()
        removed = await db.cleanup_orders(days=45)
        if removed:
            log.info("Removed %s old orders", removed)

        bot = Bot(
            config.bot_token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        renderer = Renderer(config)
        notifier = Notifier(bot, db, renderer, config)
        collector = Collector(config, db, notifier)
        scheduler = Scheduler(config, db, collector)

        dp = Dispatcher(
            storage=MemoryStorage(),
            db=db,
            config=config,
            renderer=renderer,
            notifier=notifier,
            collector=collector,
            scheduler=scheduler,
        )
        dp.message.middleware(AccessMiddleware())
        dp.callback_query.middleware(AccessMiddleware())
        setup_routers(dp)

        @dp.errors()
        async def on_error(event: ErrorEvent) -> bool:
            log.exception("Unhandled update error: %s", event.exception)
            return True

        await bot.set_my_commands(
            [
                BotCommand(command="start", description="Головне меню"),
                BotCommand(command="menu", description="Меню"),
                BotCommand(command="check", description="Перевірити джерела зараз"),
                BotCommand(command="status", description="Статус джерел"),
                BotCommand(command="cancel", description="Скасувати дію"),
                BotCommand(command="help", description="Довідка"),
            ]
        )

        if config.startup_message:
            await notifier.send_text(
                "🤖 <b>VibeParser запущено.</b> Слідкую за новими замовленнями."
            )

        # Polling cannot work while a webhook is set; also drop stale updates.
        await bot.delete_webhook(drop_pending_updates=True)

        scheduler.start()
        log.info(
            "VibeParser started | sources=%s | interval=%ss | screenshot=%s | frozen=%s",
            ",".join(await db.get_enabled_sources()),
            await db.get_int("poll_interval", config.poll_interval),
            config.screenshot_mode,
            is_frozen(),
        )
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
        return EXIT_OK
    finally:
        log.info("Shutting down…")
        if scheduler is not None:
            await scheduler.stop()
        if collector is not None:
            await collector.close()
        if renderer is not None:
            await renderer.close()
        if bot is not None:
            await bot.session.close()
        await db.close()
        instance.release()


def main() -> None:
    _configure_stdio()

    # The same executable doubles as a small diagnostic CLI:
    #   VibeParser.exe demo
    #   VibeParser.exe sources --source freelancehunt
    #   VibeParser.exe poll --render 3
    #   VibeParser.exe status
    if len(sys.argv) > 1 and sys.argv[1] in CLI_COMMANDS:
        from app.cli import main as cli_main

        try:
            cli_main()
        except KeyboardInterrupt:
            pass
        except Exception:  # noqa: BLE001 - show a readable error in a frozen app
            traceback.print_exc()
            _pause()
        return

    try:
        code = asyncio.run(run())
    except (KeyboardInterrupt, SystemExit):
        return
    except TelegramUnauthorizedError:
        print(
            "\n❌ Telegram відхилив BOT_TOKEN.\n"
            "Перевір, що токен скопійований повністю і не відкликаний у @BotFather.\n"
        )
        _offer_env_edit()
        _pause()
        return
    except TelegramConflictError:
        print(
            "\n⚠️ Конфлікт: цей бот уже десь запущений (інше вікно, сервер або Docker).\n"
            "Зупини інший процес і запусти VibeParser знову.\n"
        )
        _pause()
        return
    except ValidationError as exc:
        print(f"\n❌ Помилка у .env:\n{exc}\n")
        _pause()
        return
    except Exception:  # noqa: BLE001 - never close the window without a hint
        log.exception("Fatal error")
        traceback.print_exc()
        _pause()
        return

    if code == EXIT_CONFIG:
        _offer_env_edit()
    _pause()


if __name__ == "__main__":
    main()
