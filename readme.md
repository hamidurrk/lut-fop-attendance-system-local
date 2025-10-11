# LUT FoP Attendance System

A desktop application for managing attendance sessions in Foundations of Programming courses. The UI is built with CustomTkinter and now ships with a Visual Studio Code inspired dark theme, intelligent navigation controls, and a reliable SQLite-backed service layer.

## Why this project exists

Manual attendance tracking quickly becomes inconsistent across chapters, rooms, and campuses. This tool centralises session creation, duplicate prevention, and live logging in a single workflow that is ready for QR scanning and automation.

## Key features

- Dark theme applied across all views for a familiar developer experience.
- Collapsible navigation pane that automatically folds away and disables while a session is running.
- Guided session launcher that captures campus, weekday, hours, chapter, and week with duplicate safeguards.
- Manual entry form with contextual status feedback and recent attendee stream with relative timestamps.
- Service layer enforcing unique attendance records per session and exposing helper queries for UI components.
- SQLite schema and migrations tailored for multi-campus programmes, auto-initialised on first launch.
- Packaging scaffolds for Windows, macOS, and Linux, plus Selenium and QR decoder stubs for future automation.

## Technology stack

| Layer            | Details                                                                 |
|------------------|-------------------------------------------------------------------------| 
| UI               | CustomTkinter, theme tokens in `src/attendance_app/ui/theme.py`         |
| Services         | `AttendanceService` orchestrating sessions and attendance records       |
| Data storage     | SQLite database at `data/attendance.db` with migration support          |
| Automation stubs | Selenium scaffolding for portal scraping, QR scanning placeholder       |
| Testing          | Pytest suite in `tests/` with regression coverage                       |

## Repository layout

```
├── assets/                     # Static assets bundled with distributions
├── build_scripts/              # Cross-platform packaging helpers and PyInstaller spec
├── data/                       # Default location for the SQLite database file
├── requirements.txt            # Runtime and tooling dependencies
├── setup.py                    # Packaging metadata and entry points
├── src/attendance_app/
│   ├── automation/             # Selenium and future QR automation scaffolding
│   ├── config/                 # Environment and settings management
│   ├── data/                   # Database utilities, migrations, and bootstrap logic
│   ├── models/                 # Domain dataclasses (sessions, students, records)
│   ├── services/               # Business logic layer with validation and duplication checks
│   ├── ui/                     # CustomTkinter app shell, views, and theme tokens
│   └── utils/                  # Shared helpers (time formatting, parsing)
└── tests/                      # Pytest regression tests for utilities and services
```

## Prerequisites

- Python 3.10 or newer (tested with 3.13)
- Windows 10/11 for the primary desktop build; macOS and Linux are supported via PyInstaller
- Optional: platform camera drivers for QR scanning experiments
- Optional: Google Chrome, Edge, or Chromium plus matching Selenium WebDriver for automation work

## Quick start

Clone or download the repository, then create a virtual environment and install dependencies:

```powershell
cd c:\Users\Hamidur\Documents\lut-fop-attendance-system-local
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Launch the application:

```powershell
python -m attendance_app.main
```

On first launch the app creates `data/attendance.db`, applies migrations, and displays the themed UI. Start a session from the left navigation to see the collapsible behaviour and real-time status feedback.

## Running tests

Execute the regression suite with:

```powershell
pytest
```

The suite covers time formatting utilities and the attendance service logic. Add new tests for UI behaviour when introducing additional workflows.

## Packaging

Windows build (PowerShell):

```powershell
./build_scripts/build_windows.ps1
```

macOS build:

```bash
chmod +x build_scripts/build_macos.sh
./build_scripts/build_macos.sh
```

Linux build:

```bash
chmod +x build_scripts/build_linux.sh
./build_scripts/build_linux.sh
```

Artifacts are emitted to `dist/`. Pass `--onefile` to produce a single binary when using PyInstaller.

## Configuration notes

- Default settings are defined in `src/attendance_app/config/settings.py`. Override values via `Settings` UI panel if needed.
- `data/attendance.db` can be replaced with a shared network path for multi-machine access; update the configuration accordingly.
- Theme colours are centralised in `src/attendance_app/ui/theme.py` so additional views stay visually consistent.

## Contributing

1. Fork or branch from `main`.
2. Run `pytest` before submitting changes.
3. Document new configuration flags, commands, or dependencies in this README.

Issues and feature requests are welcome; please include reproduction steps and environment details.

