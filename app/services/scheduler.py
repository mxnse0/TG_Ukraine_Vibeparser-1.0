"""Background polling loop."""

from __future__ import annotations

import asyncio
import logging
import time

from app.config import Settings
from app.db import Database
from app.services.collector import Collector

log = logging.getLogger(__name__)


class Scheduler:
    def __init__(self, config: Settings, db: Database, collector: Collector) -> None:
        self.config = config
        self.db = db
        self.collector = collector
        self.started_at = time.time()
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._loop(), name="vibeparser-scheduler")

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            self._task = None

    async def _loop(self) -> None:
        # Give aiogram a moment to start, then do the first poll.
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=5)
            return
        except asyncio.TimeoutError:
            pass

        while not self._stop.is_set():
            interval = max(20, await self.db.get_int("poll_interval", self.config.poll_interval))
            try:
                await self.collector.collect_once()
            except Exception:  # noqa: BLE001 - keep the loop alive
                log.exception("Unhandled error during polling")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=interval)
            except asyncio.TimeoutError:
                continue
