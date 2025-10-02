from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from selenium.webdriver.remote.webdriver import WebDriver


@dataclass
class AuthCredentials:
    username: str
    password: str


class CourseScraper:
    def __init__(self, driver: WebDriver) -> None:
        self._driver = driver

    def login(self, url: str, credentials: AuthCredentials) -> None:
        raise NotImplementedError("Implement Selenium login flow for your LMS.")

    def fetch_attendance_data(self) -> Iterable[dict]:
        raise NotImplementedError("Implement scraping logic relevant to the platform.")
