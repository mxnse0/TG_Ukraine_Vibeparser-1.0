"""SQLite storage for orders, saved resumes/templates, settings and source health."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import aiosqlite

from app.models import LibraryItem, Order
from app.utils.time import utc_iso

DEFAULT_SETTINGS: dict[str, str] = {
    "owner_id": "",
    "keywords": "",
    "exclude_keywords": "",
    "min_budget": "0",
    "max_budget": "0",
    "skip_no_budget": "0",
    "enabled_sources": "freelancehunt,weblancer,freelance_ua,freelancer",
    "poll_interval": "75",
    "notify_limit": "12",
    "notifications_enabled": "1",
    "first_run_done": "0",
    "last_poll": "",
    "last_poll_new": "0",
    "last_poll_error": "",
}


class Database:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.conn: aiosqlite.Connection | None = None
        self._write_lock = asyncio.Lock()

    async def connect(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = await aiosqlite.connect(self.path)
        self.conn.row_factory = aiosqlite.Row
        await self.conn.execute("PRAGMA journal_mode=WAL")
        await self.conn.execute("PRAGMA foreign_keys=ON")
        await self.conn.execute("PRAGMA busy_timeout=5000")
        await self.conn.commit()

    async def close(self) -> None:
        if self.conn is not None:
            await self.conn.close()
            self.conn = None

    def _db(self) -> aiosqlite.Connection:
        if self.conn is None:
            raise RuntimeError("Database is not connected")
        return self.conn

    async def init(self) -> None:
        db = self._db()
        await db.executescript(
            """
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                external_id TEXT NOT NULL,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                budget_text TEXT NOT NULL DEFAULT '',
                budget_min REAL,
                budget_max REAL,
                currency TEXT,
                category TEXT NOT NULL DEFAULT '',
                tags TEXT NOT NULL DEFAULT '[]',
                published_at TEXT,
                fetched_at TEXT NOT NULL,
                notified INTEGER NOT NULL DEFAULT 0,
                search_text TEXT NOT NULL DEFAULT '',
                UNIQUE(source, external_id)
            );
            CREATE INDEX IF NOT EXISTS idx_orders_fetched ON orders(fetched_at DESC);
            CREATE INDEX IF NOT EXISTS idx_orders_source ON orders(source, fetched_at DESC);

            CREATE TABLE IF NOT EXISTS library (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL CHECK(kind IN ('resume', 'template')),
                title TEXT NOT NULL,
                text TEXT,
                file_id TEXT,
                file_name TEXT,
                mime_type TEXT,
                local_path TEXT,
                is_default INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_library_kind ON library(kind, created_at DESC);

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS source_state (
                source TEXT PRIMARY KEY,
                last_run TEXT,
                last_ok TEXT,
                last_error TEXT,
                last_count INTEGER NOT NULL DEFAULT 0,
                total_new INTEGER NOT NULL DEFAULT 0
            );
            """
        )
        for key, value in DEFAULT_SETTINGS.items():
            await db.execute(
                "INSERT OR IGNORE INTO settings(key, value) VALUES(?, ?)", (key, value)
            )
        await db.commit()
        await self._migrate_search_text()

    async def _migrate_search_text(self) -> None:
        """Add and backfill ``orders.search_text`` for databases from older builds.

        SQLite's built-in ``lower()`` only folds ASCII, so Ukrainian searches
        such as "дизайн" would miss "Дизайн". We store a Python-casefolded copy
        and search against it instead.
        """
        db = self._db()
        async with db.execute("PRAGMA table_info(orders)") as cur:
            columns = {row["name"] for row in await cur.fetchall()}
        if "search_text" not in columns:
            await db.execute(
                "ALTER TABLE orders ADD COLUMN search_text TEXT NOT NULL DEFAULT ''"
            )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_orders_search ON orders(search_text)"
        )
        await db.commit()

        async with db.execute(
            "SELECT id, title, description FROM orders WHERE search_text = ''"
        ) as cur:
            rows = await cur.fetchall()
        if not rows:
            return
        updates = [
            (f"{row['title']} {row['description']}".casefold(), row["id"])
            for row in rows
        ]
        async with self._write_lock:
            await db.executemany("UPDATE orders SET search_text = ? WHERE id = ?", updates)
            await db.commit()

    # ------------------------------------------------------------------ settings
    async def get_setting(self, key: str, default: str = "") -> str:
        async with self._db().execute("SELECT value FROM settings WHERE key = ?", (key,)) as cur:
            row = await cur.fetchone()
        return row["value"] if row else default

    async def set_setting(self, key: str, value: str | int | float | bool) -> None:
        if isinstance(value, bool):
            value = "1" if value else "0"
        async with self._write_lock:
            await self._db().execute(
                "INSERT INTO settings(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, str(value)),
            )
            await self._db().commit()

    async def get_bool(self, key: str, default: bool = False) -> bool:
        value = await self.get_setting(key, "1" if default else "0")
        return value.strip().lower() in {"1", "true", "yes", "on"}

    async def get_int(self, key: str, default: int) -> int:
        try:
            return int(await self.get_setting(key, str(default)))
        except ValueError:
            return default

    async def get_float(self, key: str, default: float) -> float:
        try:
            return float(await self.get_setting(key, str(default)))
        except ValueError:
            return default

    async def get_enabled_sources(self) -> list[str]:
        raw = await self.get_setting("enabled_sources", "")
        return [item.strip() for item in raw.split(",") if item.strip()]

    # -------------------------------------------------------------------- orders
    async def add_order(self, order: Order) -> int | None:
        """Insert an order. Returns the new row id, or None if it was already seen."""

        tags = json.dumps(order.tags[:12], ensure_ascii=False)
        published = order.published_at.isoformat() if order.published_at else None
        search_text = f"{order.title} {order.description}".casefold()
        async with self._write_lock:
            cur = await self._db().execute(
                """
                INSERT OR IGNORE INTO orders
                    (source, external_id, title, url, description, budget_text,
                     budget_min, budget_max, currency, category, tags, published_at,
                     fetched_at, notified, search_text)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
                """,
                (
                    order.source,
                    order.external_id,
                    order.title,
                    order.url,
                    order.description,
                    order.budget_text,
                    order.budget_min,
                    order.budget_max,
                    order.currency,
                    order.category,
                    tags,
                    published,
                    utc_iso(),
                    search_text,
                ),
            )
            await self._db().commit()
            if cur.rowcount == 0:
                return None
            return int(cur.lastrowid)

    async def mark_notified(self, order_id: int) -> None:
        async with self._write_lock:
            await self._db().execute("UPDATE orders SET notified = 1 WHERE id = ?", (order_id,))
            await self._db().commit()

    async def mark_notified_many(self, order_ids: list[int]) -> None:
        if not order_ids:
            return
        placeholders = ",".join("?" for _ in order_ids)
        async with self._write_lock:
            await self._db().execute(
                f"UPDATE orders SET notified = 1 WHERE id IN ({placeholders})",
                tuple(order_ids),
            )
            await self._db().commit()

    async def mark_all_notified(self) -> None:
        async with self._write_lock:
            await self._db().execute("UPDATE orders SET notified = 1 WHERE notified = 0")
            await self._db().commit()

    async def get_order(self, order_id: int) -> aiosqlite.Row | None:
        async with self._db().execute("SELECT * FROM orders WHERE id = ?", (order_id,)) as cur:
            return await cur.fetchone()

    async def recent_orders(
        self, *, limit: int = 10, offset: int = 0, search: str | None = None
    ) -> list[aiosqlite.Row]:
        if search:
            pattern = f"%{search.casefold()}%"
            sql = (
                "SELECT * FROM orders WHERE search_text LIKE ? "
                "ORDER BY id DESC LIMIT ? OFFSET ?"
            )
            params: tuple = (pattern, limit, offset)
        else:
            sql = "SELECT * FROM orders ORDER BY id DESC LIMIT ? OFFSET ?"
            params = (limit, offset)
        async with self._db().execute(sql, params) as cur:
            return list(await cur.fetchall())

    async def count_orders(self) -> int:
        async with self._db().execute("SELECT COUNT(*) AS c FROM orders") as cur:
            row = await cur.fetchone()
        return int(row["c"]) if row else 0

    async def count_orders_search(self, search: str) -> int:
        pattern = f"%{search.casefold()}%"
        async with self._db().execute(
            "SELECT COUNT(*) AS c FROM orders WHERE search_text LIKE ?",
            (pattern,),
        ) as cur:
            row = await cur.fetchone()
        return int(row["c"]) if row else 0

    async def count_orders_since(self, iso_date: str) -> int:
        async with self._db().execute(
            "SELECT COUNT(*) AS c FROM orders WHERE fetched_at >= ?", (iso_date,)
        ) as cur:
            row = await cur.fetchone()
        return int(row["c"]) if row else 0

    async def count_by_source(self) -> dict[str, int]:
        async with self._db().execute(
            "SELECT source, COUNT(*) AS c FROM orders GROUP BY source"
        ) as cur:
            rows = await cur.fetchall()
        return {row["source"]: int(row["c"]) for row in rows}

    async def cleanup_orders(self, days: int = 45) -> int:
        threshold = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
        async with self._write_lock:
            cur = await self._db().execute(
                "DELETE FROM orders WHERE fetched_at < ?", (threshold,)
            )
            await self._db().commit()
            return cur.rowcount

    # ------------------------------------------------------------------- library
    async def library_add(
        self,
        *,
        kind: str,
        title: str,
        text: str | None = None,
        file_id: str | None = None,
        file_name: str | None = None,
        mime_type: str | None = None,
        local_path: str | None = None,
    ) -> int:
        created = utc_iso()
        async with self._write_lock:
            cur = await self._db().execute(
                """
                INSERT INTO library(kind, title, text, file_id, file_name, mime_type,
                                    local_path, is_default, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)
                """,
                (kind, title, text, file_id, file_name, mime_type, local_path, created),
            )
            new_id = int(cur.lastrowid)
            # First item of its kind becomes the default automatically.
            async with self._db().execute(
                "SELECT COUNT(*) AS c FROM library WHERE kind = ?", (kind,)
            ) as count_cur:
                row = await count_cur.fetchone()
            if row and int(row["c"]) == 1:
                await self._db().execute(
                    "UPDATE library SET is_default = 1 WHERE id = ?", (new_id,)
                )
            await self._db().commit()
            return new_id

    async def library_list(self, kind: str) -> list[LibraryItem]:
        async with self._db().execute(
            "SELECT * FROM library WHERE kind = ? ORDER BY is_default DESC, id DESC", (kind,)
        ) as cur:
            rows = await cur.fetchall()
        return [self._library_item(row) for row in rows]

    async def library_get(self, item_id: int) -> LibraryItem | None:
        async with self._db().execute("SELECT * FROM library WHERE id = ?", (item_id,)) as cur:
            row = await cur.fetchone()
        return self._library_item(row) if row else None

    async def library_default(self, kind: str) -> LibraryItem | None:
        async with self._db().execute(
            "SELECT * FROM library WHERE kind = ? ORDER BY is_default DESC, id DESC LIMIT 1",
            (kind,),
        ) as cur:
            row = await cur.fetchone()
        return self._library_item(row) if row else None

    async def library_set_default(self, item_id: int) -> None:
        item = await self.library_get(item_id)
        if item is None:
            return
        async with self._write_lock:
            await self._db().execute(
                "UPDATE library SET is_default = 0 WHERE kind = ?", (item.kind,)
            )
            await self._db().execute(
                "UPDATE library SET is_default = 1 WHERE id = ?", (item_id,)
            )
            await self._db().commit()

    async def library_delete(self, item_id: int) -> LibraryItem | None:
        item = await self.library_get(item_id)
        if item is None:
            return None
        async with self._write_lock:
            await self._db().execute("DELETE FROM library WHERE id = ?", (item_id,))
            if item.is_default:
                async with self._db().execute(
                    "SELECT id FROM library WHERE kind = ? ORDER BY id DESC LIMIT 1",
                    (item.kind,),
                ) as cur:
                    row = await cur.fetchone()
                if row:
                    await self._db().execute(
                        "UPDATE library SET is_default = 1 WHERE id = ?", (row["id"],)
                    )
            await self._db().commit()
        return item

    @staticmethod
    def _library_item(row: aiosqlite.Row) -> LibraryItem:
        return LibraryItem(
            id=int(row["id"]),
            kind=row["kind"],
            title=row["title"],
            text=row["text"],
            file_id=row["file_id"],
            file_name=row["file_name"],
            mime_type=row["mime_type"],
            local_path=row["local_path"],
            is_default=bool(row["is_default"]),
            created_at=row["created_at"],
        )

    # --------------------------------------------------------------- source state
    async def update_source_state(
        self,
        source: str,
        *,
        ok: bool,
        count: int = 0,
        error: str = "",
        new_count: int = 0,
    ) -> None:
        now = utc_iso()
        async with self._write_lock:
            await self._db().execute(
                """
                INSERT INTO source_state(source, last_run, last_ok, last_error, last_count, total_new)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(source) DO UPDATE SET
                    last_run = excluded.last_run,
                    last_ok = CASE WHEN excluded.last_error = '' THEN excluded.last_ok ELSE source_state.last_ok END,
                    last_error = excluded.last_error,
                    last_count = excluded.last_count,
                    total_new = source_state.total_new + excluded.total_new
                """,
                (source, now, now if ok else None, error, count, new_count),
            )
            await self._db().commit()

    async def source_states(self) -> dict[str, aiosqlite.Row]:
        async with self._db().execute("SELECT * FROM source_state") as cur:
            rows = await cur.fetchall()
        return {row["source"]: row for row in rows}

    async def reset_source_state(self, source: str) -> None:
        async with self._write_lock:
            await self._db().execute("DELETE FROM source_state WHERE source = ?", (source,))
            await self._db().commit()
