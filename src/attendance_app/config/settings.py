from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parents[2]
ENV_PATH = BASE_DIR / ".env"
load_dotenv(ENV_PATH)


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "LUT FoP Attendance System")
    database_path: Path = Path(os.getenv("DATABASE_PATH", BASE_DIR / "data" / "attendance.db"))
    selenium_driver_path: Path | None = (
        Path(driver_path) if (driver_path := os.getenv("SELENIUM_DRIVER_PATH")) else None
    )
    qr_camera_index: int = int(os.getenv("QR_CAMERA_INDEX", "0"))


settings = Settings()
