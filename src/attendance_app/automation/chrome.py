from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

try:  # pragma: no cover - import guard for static analysis
    from webdriver_manager.chrome import ChromeDriverManager
except ImportError as exc:  # pragma: no cover - missing dependency
    raise RuntimeError(
        "webdriver-manager is required for Chrome automation support."
    ) from exc

from attendance_app.config.settings import settings


class ChromeAutomationError(RuntimeError):
    """Raised when the automated Chrome session cannot be launched."""


@dataclass(slots=True)
class ChromeRemoteController:
    """Manage a long-lived Chrome instance exposed via the remote debugging protocol."""

    _remote_port: int = settings.chrome_remote_debug_port
    _user_data_dir: Path = settings.chrome_user_data_dir
    _binary_path: Optional[Path] = settings.chrome_binary_path
    _driver_path: Optional[Path] = settings.selenium_driver_path
    _driver: Optional[webdriver.Chrome] = field(init=False, default=None, repr=False)
    _lock: threading.Lock = field(init=False, default_factory=threading.Lock, repr=False)

    def __post_init__(self) -> None:  # pragma: no cover - simple path preparation
        self._user_data_dir.mkdir(parents=True, exist_ok=True)
        if self._binary_path is None:
            self._binary_path = self._discover_chrome_binary()
        if self._binary_path is None:
            raise ChromeAutomationError("Google Chrome executable not found. Set CHROME_BINARY_PATH.")

    def open_browser(self) -> webdriver.Chrome:
        """Ensure the remote Chrome instance is running and return a connected WebDriver."""
        with self._lock:
            self._ensure_remote_browser()
            return self._ensure_driver()

    def is_browser_open(self) -> bool:
        """Return True if the remote debugging Chrome instance appears to be running."""
        with self._lock:
            return self._is_port_open()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _ensure_remote_browser(self) -> None:
        if self._is_port_open():
            return
        command = [
            str(self._binary_path),
            f"--remote-debugging-port={self._remote_port}",
            f"--user-data-dir={self._user_data_dir}",
            "--no-first-run",
            "--no-default-browser-check",
        ]
        if sys.platform.startswith("linux"):
            command.append("--disable-dev-shm-usage")

        popen_kwargs: dict = {
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
        }
        if os.name == "nt":  # Windows
            popen_kwargs["creationflags"] = (
                getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                | getattr(subprocess, "DETACHED_PROCESS", 0)
            )
        else:  # POSIX
            popen_kwargs["start_new_session"] = True

        try:
            subprocess.Popen(command, **popen_kwargs)  # noqa: S603, S607 - launching trusted binary
        except FileNotFoundError as exc:  # pragma: no cover - configuration issue
            raise ChromeAutomationError(f"Chrome binary not found: {self._binary_path}") from exc

        self._wait_for_port()

    def _ensure_driver(self) -> webdriver.Chrome:
        if self._driver is not None:
            try:
                # Trigger a lightweight command to verify the connection
                self._driver.title  # type: ignore[attr-defined]
                return self._driver
            except WebDriverException:
                try:
                    self._driver.quit()
                except Exception:  # pragma: no cover - best effort cleanup
                    pass
                self._driver = None

        options = Options()
        options.add_experimental_option(
            "debuggerAddress", f"localhost:{self._remote_port}"
        )

        driver_path = self._driver_path or Path(ChromeDriverManager().install())
        service = Service(str(driver_path))

        try:
            driver = webdriver.Chrome(service=service, options=options)
        except WebDriverException as exc:
            raise ChromeAutomationError(
                "Failed to connect to the remote Chrome instance. Make sure the browser started "
                "with remote debugging is still running."
            ) from exc
        self._driver = driver
        return driver

    def _is_port_open(self) -> bool:
        try:
            with socket.create_connection(("localhost", self._remote_port), timeout=0.5):
                return True
        except OSError:
            return False

    def _wait_for_port(self, timeout: float = 10.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._is_port_open():
                return
            time.sleep(0.2)
        raise ChromeAutomationError(
            f"Chrome failed to open remote debugging port {self._remote_port} within {timeout} seconds."
        )

    @staticmethod
    def _discover_chrome_binary() -> Optional[Path]:
        candidates: list[Path] = []
        if os.name == "nt":
            potential = [
                Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
                Path("C:/Program Files (x86)/Google/Chrome/Application/chrome.exe"),
            ]
            candidates.extend(potential)
        else:
            for executable in ("google-chrome", "chromium-browser", "chromium"):
                located = shutil.which(executable)
                if located:
                    candidates.append(Path(located))

        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None
