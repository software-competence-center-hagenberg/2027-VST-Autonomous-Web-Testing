"""In-memory latest-frame channels used by per-task MJPEG streams."""
from __future__ import annotations

import asyncio


class BrowserFrameStream:
    def __init__(self) -> None:
        self._condition = asyncio.Condition()
        self._frame: bytes | None = None
        self._version = 0
        self._closed = False

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def has_frame(self) -> bool:
        return self._frame is not None

    async def publish(self, frame: bytes) -> None:
        async with self._condition:
            self._frame = frame
            self._version += 1
            self._condition.notify_all()

    async def close(self) -> None:
        async with self._condition:
            self._closed = True
            self._condition.notify_all()

    async def wait_for_frame(self, previous_version: int) -> tuple[bytes | None, int, bool]:
        async with self._condition:
            await self._condition.wait_for(
                lambda: self._version > previous_version or self._closed
            )
            frame = self._frame if self._version > previous_version else None
            return frame, self._version, self._closed


_streams: dict[str, BrowserFrameStream] = {}


def get_browser_stream(task_id: str) -> BrowserFrameStream:
    stream = _streams.get(task_id)
    if stream is None or stream.closed:
        stream = BrowserFrameStream()
        _streams[task_id] = stream
    return stream


def find_browser_stream(task_id: str) -> BrowserFrameStream | None:
    return _streams.get(task_id)


async def close_browser_stream(task_id: str) -> None:
    stream = _streams.get(task_id)
    if stream is not None:
        await stream.close()
