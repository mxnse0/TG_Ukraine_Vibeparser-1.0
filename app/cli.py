"""Command-line tools for testing sources and rendering cards without Telegram."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import httpx

from app.config import Settings
from app.db import Database
from app.parsers import build_parsers, parser_meta
from app.services.collector import Collector
from app.services.renderer import Renderer, demo_order
from app.utils.rows import row_to_order
from app.utils.time import human_time, parse_datetime


async def cmd_sources(args: argparse.Namespace) -> None:
    config = Settings()
    config.ensure_dirs()
    parsers = build_parsers(config.currency_rates)
    selected = [name for name in parsers if not args.source or name == args.source]
    if not selected:
        print(f"Unknown source. Available: {', '.join(parsers)}")
        return

    headers = {
        "User-Agent": config.user_agent,
        "Accept-Language": "uk-UA,uk;q=0.9,en;q=0.8",
    }
    async with httpx.AsyncClient(
        headers=headers, follow_redirects=True, timeout=config.http_timeout
    ) as client:
        tasks = [
            parsers[name].fetch(client, pages=min(parsers[name].max_pages, args.pages))
            for name in selected
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    meta = parser_meta()
    for name, result in zip(selected, results):
        print(f"\n=== {meta[name]['title']} ({name}) ===")
        if isinstance(result, Exception):
            print(f"  ERROR: {type(result).__name__}: {result}")
            continue
        print(f"  OK: {len(result)} orders")
        for order in result[: args.limit]:
            print(
                f"  • [{order.external_id}] {order.title[:80]}"
                f" | {order.budget_text or 'no budget'}"
            )
            print(f"    {order.url}")


async def cmd_poll(args: argparse.Namespace) -> None:
    config = Settings()
    config.ensure_dirs()
    db = Database(config.db_path)
    await db.connect()
    await db.init()
    collector = Collector(config, db, notifier=None)
    try:
        result = await collector.collect_once()
        print(
            f"fetched={result.fetched} new={result.new} matched={result.matched} "
            f"notified={result.notified} duration={result.duration:.1f}s"
        )
        if result.errors:
            print("errors:")
            for source, error in result.errors.items():
                print(f"  - {source}: {error}")
        if args.render:
            renderer = Renderer(config)
            rows = await db.recent_orders(limit=args.render)
            out_dir = config.data_dir / "previews"
            for row in rows:
                image = await renderer.render(row_to_order(row))
                path = out_dir / f"order_{row['id']}.jpg"
                path.write_bytes(image)
                print(f"preview: {path}")
            await renderer.close()
    finally:
        await collector.close()
        await db.close()


async def cmd_demo(args: argparse.Namespace) -> None:
    config = Settings()
    config.ensure_dirs()
    renderer = Renderer(config)
    try:
        image = await renderer.render(demo_order())
    finally:
        await renderer.close()
    path = config.data_dir / "previews" / "demo.jpg"
    path.write_bytes(image)
    print(f"demo card: {path} ({len(image) / 1024:.0f} KB)")


async def cmd_status(args: argparse.Namespace) -> None:
    config = Settings()
    db = Database(config.db_path)
    await db.connect()
    await db.init()
    try:
        total = await db.count_orders()
        by_source = await db.count_by_source()
        states = await db.source_states()
        print(f"Database: {config.db_path}")
        print(f"Orders: {total}")
        for source, count in sorted(by_source.items(), key=lambda item: -item[1]):
            state = states.get(source)
            last = human_time(
                parse_datetime(state["last_ok"]) if state and state["last_ok"] else None,
                config.tz,
            )
            print(f"  {source:15} {count:5}  last_ok={last}")
        last_poll = parse_datetime(await db.get_setting("last_poll", ""))
        print(f"Last poll: {human_time(last_poll, config.tz)}")
    finally:
        await db.close()


def build_parser() -> argparse.ArgumentParser:
    prog = Path(sys.executable).name if getattr(sys, "frozen", False) else "python -m app.cli"
    parser = argparse.ArgumentParser(
        prog=prog,
        description="VibeParser CLI: test sources, poll once, render cards.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sources = sub.add_parser("sources", help="fetch each source once and print results")
    sources.add_argument("--source", help="only this source (e.g. freelancehunt)")
    sources.add_argument("--pages", type=int, default=1)
    sources.add_argument("--limit", type=int, default=5)
    sources.set_defaults(func=cmd_sources)

    poll = sub.add_parser("poll", help="run one real poll against the database")
    poll.add_argument("--render", type=int, default=0, metavar="N", help="render N latest cards")
    poll.set_defaults(func=cmd_poll)

    demo = sub.add_parser("demo", help="render a demo order card")
    demo.set_defaults(func=cmd_demo)

    status = sub.add_parser("status", help="show database statistics")
    status.set_defaults(func=cmd_status)

    return parser


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args()
    asyncio.run(args.func(args))


if __name__ == "__main__":
    main()
