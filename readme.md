# Queue - LUT FoP Attendance System

A desktop application for managing attendance and grading in the exercise sessions of the Foundations of Programming course. The system has QR-based quick attendance marking, auto-bonus point registering, intelligent record management, automated reliable grading in Moodle and a consistent SQLite-backed service layer.

## Why this project exists

Manual attendance tracking quickly becomes tiresome across chapters, rooms, and campuses. Queue focuses on attendance logging, bonus tracking, and grading automation so instructors can focus on teaching instead of paperwork. It also removes the need to maintain separate tools for regular attendance.

## Key features

- **Themed, responsive UI**  
  Dark theme applied across every view, with layouts that adapt to narrow widths. Auto-grader detail view reflows into stacked panels below 1080 px, making side-by-side work with Chrome painless.

- **Navigation that reacts to workflow**  
  Collapsible sidebar automatically hides while a live session is running; Manage Records view now refreshes session data whenever it opens so instructors always start with the latest totals.

- **Guided session launcher with duplicate guardrails**  
  Start sessions by choosing campus, weekday, hours, and chapter. If a matching session already exists, Queue offers to reopen it instead of blocking the instructor.

- **Realtime attendance capture**  
  Manual form with status feedback, recent attendee stream, optional auto-point settings, and QR scanner integration. Bonus tab mirrors the workflow with CodeGrade-handling helpers.

- **Manage Records power tools**  
  - Auto-match bonus allocations with fuzzy-name detection.
  - Highlight unmatched (red) or fuzzy (amber) bonuses and clear them automatically after saving.
  - One-click delete per session with irreversible warning, removing attendance and bonus records together.

- **Auto-grader automation workflow**  
  - Launches Chrome via Selenium, opens CodeGrade submissions, and posts results back to the database.
  - Background errors surface in both UI and console with stack traces.
  - Active student row is highlighted and auto-scrolled into view while grading runs.
  - Start/stop/pause controls stay responsive even after failures thanks to improved thread cleanup.

- **Asset-aware UI utilities**  
  Central icon loader (`load_icon_image`) keeps buttons consistent, including the new trash control in Manage Records and navigation icons.

- **Reliable service layer**  
  `AttendanceService` handles deduplication, confirmation, grading status updates, and now session deletion cascades (attendance + bonus records).

- **Extensible automation scaffolding**  
  Selenium controller, CodeGrade interaction shell, QR automation stubs, and Chrome profile bootstrapping live under `src/attendance_app/automation/`.

- **Cross-platform packaging**  
  PyInstaller scripts for Windows, macOS, and Linux (with one-file modes) plus an assets folder ready for distribution.

## Technology stack

| Layer            | Details                                                                 |
|------------------|-------------------------------------------------------------------------|
| UI               | CustomTkinter, responsive layouts, theme tokens in `ui/theme.py`        |
| Services         | `AttendanceService` for session lifecycle & cascaded deletions          |
| Data storage     | SQLite (`data/attendance.db`) with migrations and bootstrap helpers     |
| Automation       | Selenium-based Chrome driver, QR scaffolding, bonus workflows           |
| Testing          | Pytest suite under `tests/` covering services and utilities             |

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
- Windows 10/11 for the primary desktop build; macOS and Linux are supported via PyInstaller but not tested yet
- Optional Automation: Google Chrome for automation work

## Quick start

There are two ways:
1. Download the latest executable (.exe) from the release and run it. On first launch the app creates `data/attendance.db`, applies migrations, and displays the UI. Start a session from the left navigation to see the collapsible behaviour and real-time status feedback.
Or,
2. Clone or download the repository, then create a virtual environment and install dependencies:

```powershell
cd c:\path\to\the\repo\lut-fop-attendance-system-local
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Launch the application:

```powershell
python -m attendance_app.main
```

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

macOS build (not tested):

```bash
chmod +x build_scripts/build_macos.sh
./build_scripts/build_macos.sh
```

Linux build (not tested):

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

## LICENSE
This software is licensed under MIT License. Check [LICENSE](./LICENSE) for details.