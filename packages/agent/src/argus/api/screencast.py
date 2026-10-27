"""CDP screencast capture and bounded fan-out for live browser views."""

from __future__ import annotations

import asyncio
from typing import Any


class ScreencastHub:
    """Publish the newest browser frames and action cues to websocket clients."""

    def __init__(self, run_id: str, *, queue_size: int = 3) -> None:
        if queue_size < 2:
            raise ValueError("queue_size must be at least 2")
        self.run_id = run_id
        self.queue_size = queue_size
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self._sequence = 0
        self._latest_frame: dict[str, Any] | None = None
        self._latest_action: dict[str, Any] | None = None
        self._closed = False

    @property
    def closed(self) -> bool:
        return self._closed

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=self.queue_size)
        self._subscribers.add(queue)
        initial_messages = sorted(
            (message for message in (self._latest_action, self._latest_frame) if message is not None),
            key=lambda message: message["sequence"],
        )
        for message in initial_messages:
            self._offer(queue, message)
        if self._closed:
            self._offer(queue, {"kind": "closed", "run_id": self.run_id})
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self._subscribers.discard(queue)

    def publish_frame(self, frame: dict[str, Any]) -> None:
        message = {
            "kind": "frame",
            "run_id": self.run_id,
            "sequence": self._next_sequence(),
            "data": frame.get("data", ""),
            "metadata": frame.get("metadata", {}),
        }
        self._latest_frame = message
        self._publish(message)

    def publish_action(self, action: dict[str, Any]) -> None:
        message = {
            "kind": "action",
            "run_id": self.run_id,
            "sequence": self._next_sequence(),
            **action,
        }
        self._latest_action = message
        self._publish(message)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._publish({"kind": "closed", "run_id": self.run_id})

    def _next_sequence(self) -> int:
        self._sequence += 1
        return self._sequence

    def _publish(self, message: dict[str, Any]) -> None:
        for queue in tuple(self._subscribers):
            self._offer(queue, message)

    def _offer(self, queue: asyncio.Queue[dict[str, Any]], message: dict[str, Any]) -> None:
        if queue.full():
            queued: list[dict[str, Any]] = []
            while not queue.empty():
                queued.append(queue.get_nowait())
            drop_index = next(
                (index for index, item in enumerate(queued) if item.get("kind") == "frame"),
                0,
            )
            queued.pop(drop_index)
            for item in queued[-(self.queue_size - 1) :]:
                queue.put_nowait(item)
        queue.put_nowait(message)
