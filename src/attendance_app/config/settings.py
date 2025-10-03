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
    chrome_remote_debug_port: int = int(os.getenv("CHROME_REMOTE_DEBUG_PORT", "9222"))
    chrome_user_data_dir: Path = Path(
        os.getenv("CHROME_USER_DATA_DIR", str(BASE_DIR / "data" / "chrome-profile"))
    )
    chrome_binary_path: Path | None = (
        Path(binary_path) if (binary_path := os.getenv("CHROME_BINARY_PATH")) else None
    )
    default_bonus_points: str = "2" 
    default_attendance_points : str = "5"

settings = Settings()
