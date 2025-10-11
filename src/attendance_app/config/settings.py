from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parents[2]
ENV_PATH = BASE_DIR / ".env"
load_dotenv(ENV_PATH)

DOCUMENTS_PATH = Path(os.path.expanduser("~")) / "Documents"
APP_NAME = os.getenv("APP_NAME", "LUT FoP Attendance System")
APP_DATA_DIR = DOCUMENTS_PATH / APP_NAME

APP_DATA_DIR.mkdir(parents=True, exist_ok=True)

@dataclass(frozen=True)
class Settings:
    app_name: str = APP_NAME
    database_path: Path = Path(
        os.getenv("DATABASE_PATH", APP_DATA_DIR / "attendance.db")
    )
    selenium_driver_path: Path | None = (
        Path(driver_path) if (driver_path := os.getenv("SELENIUM_DRIVER_PATH")) else None
    )
    qr_camera_index: int = int(os.getenv("QR_CAMERA_INDEX", "0"))
    chrome_remote_debug_port: int = int(os.getenv("CHROME_REMOTE_DEBUG_PORT", "9222"))
    chrome_user_data_dir: Path = Path(
        os.getenv("CHROME_USER_DATA_DIR", str(APP_DATA_DIR / "chrome-profile"))
    )
    chrome_binary_path: Path | None = (
        Path(binary_path) if (binary_path := os.getenv("CHROME_BINARY_PATH")) else None
    )
    default_bonus_points: int = 2
    default_attendance_points: int = 5

    def __print__(self) -> str:
        return (
            f"Settings(app_name={self.app_name}, "
            f"database_path={self.database_path}, "
            f"selenium_driver_path={self.selenium_driver_path}, "
            f"qr_camera_index={self.qr_camera_index}, "
            f"chrome_remote_debug_port={self.chrome_remote_debug_port}, "
            f"chrome_user_data_dir={self.chrome_user_data_dir}, "
            f"chrome_binary_path={self.chrome_binary_path}, "
            f"default_bonus_points={self.default_bonus_points}, "
            f"default_attendance_points={self.default_attendance_points})"
        )

settings = Settings()
print(settings.__print__())