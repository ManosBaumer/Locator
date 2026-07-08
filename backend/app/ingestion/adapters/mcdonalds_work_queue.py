"""Thread-safe async work queue with snapshot support for checkpoints."""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Iterable


class McDonaldsWorkQueue:
    def __init__(self) -> None:
        self._items: deque[tuple[float, float, float] | None] = deque()
        self._unfinished = 0
        self._lock = asyncio.Lock()
        self._not_empty = asyncio.Condition(self._lock)
        self._all_done = asyncio.Condition(self._lock)

    def __len__(self) -> int:
        return sum(1 for item in self._items if item is not None)

    async def put(self, item: tuple[float, float, float]) -> None:
        async with self._not_empty:
            self._items.append(item)
            self._unfinished += 1
            self._not_empty.notify()

    async def put_many(self, items: Iterable[tuple[float, float, float]]) -> None:
        async with self._not_empty:
            for item in items:
                self._items.append(item)
                self._unfinished += 1
            self._not_empty.notify(len(self._items))

    async def put_sentinel(self) -> None:
        async with self._not_empty:
            self._items.append(None)
            self._not_empty.notify()

    async def get(self) -> tuple[float, float, float] | None:
        async with self._not_empty:
            while not self._items:
                await self._not_empty.wait()
            return self._items.popleft()

    async def task_done(self) -> None:
        async with self._all_done:
            self._unfinished -= 1
            if self._unfinished == 0:
                self._all_done.notify_all()

    async def join(self) -> None:
        async with self._all_done:
            while self._unfinished > 0:
                await self._all_done.wait()

    async def snapshot(self) -> list[tuple[float, float, float]]:
        async with self._lock:
            return [item for item in self._items if item is not None]

    async def abort(self, worker_count: int) -> int:
        """Drop pending cells and unblock workers so the crawl can exit early."""
        async with self._not_empty:
            abandoned = sum(1 for item in self._items if item is not None)
            self._items.clear()
            self._unfinished -= abandoned
            for _ in range(worker_count):
                self._items.append(None)
                self._unfinished += 1
            self._not_empty.notify(worker_count)
        async with self._all_done:
            if self._unfinished == 0:
                self._all_done.notify_all()
        return abandoned
