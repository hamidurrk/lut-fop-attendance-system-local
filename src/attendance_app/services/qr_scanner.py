from __future__ import annotations

import threading
import time
import unicodedata
from contextlib import suppress
from typing import Any, Callable, Optional

SCAN_INTERVAL_SECONDS = 0.08
DEDUP_INTERVAL_SECONDS = 0.8
PREVIEW_INTERVAL_SECONDS = 0.07
PREVIEW_MAX_WIDTH = 480


def _decode_symbol_data(raw: bytes | str) -> str:
    if not raw:
        return ""

    if isinstance(raw, str):
        decoded = raw
    else:
        try:
            decoded = raw.decode("utf-8")
        except UnicodeDecodeError:
            decoded = raw.decode("utf-8", errors="ignore")

    normalized = unicodedata.normalize("NFC", decoded)
    return normalized.strip()


class QRScanner:
    def __init__(self, camera_index: int = 0) -> None:
        self._camera_index = camera_index
        self._running = False
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

    def start(
        self,
        on_payload: Callable[[str], None],
        *,
        on_error: Optional[Callable[[str], None]] = None,
        on_frame: Optional[Callable[[Any], None]] = None,
    ) -> bool:
        """Start the background scanner loop."""

        with self._lock:
            if self._running:
                return True

            try:
                import cv2  # type: ignore[import-not-found]
                import zxingcpp  # type: ignore[import-not-found]
            except ImportError:
                if on_error:
                    on_error(
                        "Missing QR scanner dependencies. Install OpenCV (cv2) and zxing-cpp to enable scanning."
                    )
                return False

            self._stop_event.clear()

            def _runner() -> None:
                self._run_loop(on_payload, on_error, on_frame, cv2, zxingcpp)

            self._thread = threading.Thread(target=_runner, daemon=True)
            self._running = True
            self._thread.start()
            return True

    def stop(self) -> None:
        with self._lock:
            if not self._running:
                return
            self._running = False
            self._stop_event.set()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.5)
        self._thread = None

    @property
    def is_running(self) -> bool:
        return self._running

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _run_loop(
        self,
        on_payload: Callable[[str], None],
        on_error: Optional[Callable[[str], None]],
        on_frame: Optional[Callable[[Any], None]],
        cv2_module,
        zxing_module,
    ) -> None:
        capture = None
        last_payload: Optional[str] = None
        last_timestamp: float = 0.0
        last_preview: float = 0.0

        try:
            capture = self._open_capture(cv2_module, on_error)
            if capture is None:
                return

            while not self._stop_event.is_set():
                ok, frame = capture.read()
                if not ok:
                    time.sleep(SCAN_INTERVAL_SECONDS)
                    continue

                try:
                    frame = cv2_module.flip(frame, 1)
                except Exception:
                    pass

                now = time.time()

                if on_frame and (now - last_preview) >= PREVIEW_INTERVAL_SECONDS:
                    preview_frame = frame
                    if PREVIEW_MAX_WIDTH and preview_frame.shape[1] > PREVIEW_MAX_WIDTH:
                        scale = PREVIEW_MAX_WIDTH / float(preview_frame.shape[1])
                        height = int(preview_frame.shape[0] * scale)
                        preview_frame = cv2_module.resize(preview_frame, (PREVIEW_MAX_WIDTH, height))
                    try:
                        on_frame(preview_frame.copy())
                    except Exception:
                        pass
                    last_preview = now

                try:
                    decoded = zxing_module.read_barcodes(
                        frame,
                        formats=zxing_module.BarcodeFormat.QRCode,
                        try_rotate=True,
                        try_downscale=True,
                        text_mode=zxing_module.TextMode.HRI,
                    )
                except Exception:
                    decoded = []

                if not decoded:
                    time.sleep(SCAN_INTERVAL_SECONDS)
                    continue
                for obj in decoded:
                    if hasattr(obj, "valid") and not obj.valid:
                        continue
                    if getattr(obj, "error", None):
                        continue

                    payload_text = getattr(obj, "text", "")
                    payload = _decode_symbol_data(payload_text)
                    if not payload:
                        payload_bytes = getattr(obj, "bytes", b"") or b""
                        if not isinstance(payload_bytes, (bytes, bytearray)):
                            payload_bytes = bytes(payload_bytes)
                        payload = _decode_symbol_data(payload_bytes)
                    if not payload:
                        continue

                    if last_payload == payload and (now - last_timestamp) < DEDUP_INTERVAL_SECONDS:
                        continue

                    last_payload = payload
                    last_timestamp = now

                    try:
                        on_payload(payload)
                    except Exception:  # pragma: no cover - guard callback faults
                        pass

                time.sleep(SCAN_INTERVAL_SECONDS)
        finally:
            if capture is not None:
                with suppress(Exception):
                    capture.release()
            self._stop_event.clear()
            with self._lock:
                self._running = False

    def _open_capture(self, cv2_module, on_error: Optional[Callable[[str], None]]):
        capture = None
        backend_preferences = [getattr(cv2_module, "CAP_DSHOW", None), getattr(cv2_module, "CAP_ANY", None)]

        for backend in backend_preferences:
            if backend is None:
                capture = cv2_module.VideoCapture(self._camera_index)
            else:
                capture = cv2_module.VideoCapture(self._camera_index, backend)

            if capture.isOpened():
                return capture

            capture.release()
            capture = None

        if on_error:
            on_error("Unable to access the camera. Check that it is connected and not used by another app.")

        return None
