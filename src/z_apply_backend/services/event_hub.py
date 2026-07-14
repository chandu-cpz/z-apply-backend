from __future__ import annotations

import asyncio
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StoredEvent:
    id: int
    event_type: str
    data: dict[str, object]


class EventHub:
    """Small bounded fan-out hub. Slow SSE clients are disconnected intentionally."""

    def __init__(self, queue_size: int = 256) -> None:
        self._queue_size = queue_size
        self._queues: set[asyncio.Queue[StoredEvent | None]] = set()
        self._lock = asyncio.Lock()

    async def publish(self, event: StoredEvent) -> None:
        async with self._lock:
            queues = tuple(self._queues)
        for queue in queues:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # None is a deliberate disconnect marker, not a dropped event.
                while not queue.empty():
                    queue.get_nowait()
                queue.put_nowait(None)

    async def register(self) -> asyncio.Queue[StoredEvent | None]:
        queue: asyncio.Queue[StoredEvent | None] = asyncio.Queue(maxsize=self._queue_size)
        async with self._lock:
            self._queues.add(queue)
        return queue

    async def unregister(self, queue: asyncio.Queue[StoredEvent | None]) -> None:
        async with self._lock:
            self._queues.discard(queue)
