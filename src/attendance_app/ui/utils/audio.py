from __future__ import annotations

import math
import threading
from io import BytesIO

try:
    import winsound  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - non-Windows fallback
    winsound = None  # type: ignore[assignment]

_SCANNER_WAV_CACHE: bytes | None = None


def _build_wave_bytes(
    *,
    frequency_hz: int = 1800,
    duration_ms: int = 140,
    sample_rate: int = 44100,
    amplitude: float = 0.35,
) -> bytes:
    import wave

    frame_count = int(sample_rate * (duration_ms / 1000.0))
    sine_wave = bytearray()
    for index in range(frame_count):
        value = int(32767 * amplitude * math.sin(2 * math.pi * frequency_hz * index / sample_rate))
        sine_wave.extend(value.to_bytes(2, byteorder="little", signed=True))

    buffer = BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(sine_wave)
    return buffer.getvalue()


def _get_wave_bytes() -> bytes | None:
    global _SCANNER_WAV_CACHE
    if _SCANNER_WAV_CACHE is None:
        try:
            _SCANNER_WAV_CACHE = _build_wave_bytes()
        except Exception:
            _SCANNER_WAV_CACHE = b""
    return _SCANNER_WAV_CACHE or None


def _play_with_winsound() -> None:
    if winsound is None:
        return

    wave_bytes = _get_wave_bytes()
    if wave_bytes is None:
        return

    try:
        winsound.PlaySound(wave_bytes, winsound.SND_ASYNC | winsound.SND_MEMORY)
    except Exception:
        try:
            winsound.Beep(1500, 120)
        except Exception:
            pass


def _play_fallback() -> None:
    try:
        print("\a", end="", flush=True)
    except Exception:
        pass


def play_scanner_beep_async() -> None:
    def _runner() -> None:
        if winsound is not None:
            _play_with_winsound()
        else:
            _play_fallback()

    threading.Thread(target=_runner, daemon=True).start()
