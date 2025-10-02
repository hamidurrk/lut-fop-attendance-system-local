from __future__ import annotations

import sys
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
SRC_DIR = PACKAGE_DIR.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from attendance_app.ui.app import AttendanceApp

def main() -> None:
    app = AttendanceApp()
    app.run()


if __name__ == "__main__":
    main()
