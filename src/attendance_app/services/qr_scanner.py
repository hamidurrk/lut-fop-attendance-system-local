from __future__ import annotations

from typing import Callable, Iterator, Optional


class QRScanner:
    def __init__(self, camera_index: int = 0) -> None:
        self._camera_index = camera_index
        self._running = False

    def start(self, on_payload: Callable[[str], None]) -> None:
        # todo: Implement camera capture loop.
        self._running = True
        self._running = False

    def stop(self) -> None:
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running
