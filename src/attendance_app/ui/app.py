from __future__ import annotations

import customtkinter as ctk
import json
import os
import re

from attendance_app.automation import ChromeRemoteController, ChromeAutomationError, open_moodle_courses
from attendance_app.config.settings import settings
from attendance_app.data import Database
from attendance_app.services import AttendanceService
from attendance_app.ui.components.collapsible_nav import CollapsibleNav
from attendance_app.ui.navigation import NAV_ITEMS
from attendance_app.ui.placeholders import PlaceholderView
from attendance_app.ui.take_attendance_view import TakeAttendanceView
from attendance_app.ui.manage_records_view import ManageRecordsView
from attendance_app.ui.theme import VS_BG


class AttendanceApp:
    def __init__(self) -> None:
        super().__init__()

        # Set DPI awareness to handle multi-monitor setups better
        try:
            from ctypes import windll
            windll.shcore.SetProcessDpiAwareness(1)  # Process system DPI aware
        except (ImportError, AttributeError):
            pass  # Not on Windows or older Windows version

        ctk.set_appearance_mode("dark")

        self._root = ctk.CTk()
        self._root.title(settings.app_name)
        self._root.geometry("1280x720")
        self._root.minsize(1080, 640)
        self._root.configure(fg_color=VS_BG)

        self._root.grid_rowconfigure(0, weight=1)
        self._root.grid_columnconfigure(1, weight=1)

        database = Database(settings.database_path)
        self._attendance_service = AttendanceService(database)
        self._attendance_service.initialize()

        try:
            self._chrome_controller = ChromeRemoteController()
        except ChromeAutomationError:
            self._chrome_controller = None

        self._nav = CollapsibleNav(self._root, items=NAV_ITEMS, on_select=self._show_view)
        self._nav.grid(row=0, column=0, sticky="nsw")

        self._content = ctk.CTkFrame(self._root, corner_radius=0, fg_color=VS_BG)
        self._content.grid(row=0, column=1, sticky="nsew")
        self._content.grid_rowconfigure(0, weight=1)
        self._content.grid_columnconfigure(0, weight=1)

        take_attendance_view = TakeAttendanceView(
            self._content,
            self._attendance_service,
            chrome_controller=self._chrome_controller,
            on_session_started=self._handle_session_started,
            on_session_ended=self._handle_session_ended,
        )

        self._views = {
            "take_attendance": take_attendance_view,
            "history": ManageRecordsView(
                self._content,
                self._attendance_service,
            ),
            "auto_grader": PlaceholderView(
                self._content,
                title="Auto-grader",
                message="Automate grading workflows from this tab in future iterations.",
            ),
        }

        take_attendance_view.register_bonus_automation_handler(open_moodle_courses)

        for view in self._views.values():
            view.grid(row=0, column=0, sticky="nsew")

        self._show_view("take_attendance")
        self._nav.select("take_attendance")

        # Load saved window position if available
        self._restore_window_position()
        self._root.after(0, self._maximize_window)

        # Bind window movement/configure events
        self._root.bind("<Configure>", self._handle_window_configure)

        # Save position on close
        self._root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _show_view(self, key: str) -> None:
        for name, view in self._views.items():
            view.grid_remove()
        if key in self._views:
            self._views[key].grid()

    def _handle_session_started(self) -> None:
        self._nav.collapse()
        self._nav.set_navigation_enabled(False)

    def _handle_session_ended(self) -> None:
        self._nav.set_navigation_enabled(True)
        self._nav.expand()

    def _restore_window_position(self):
        """Restore window position from saved settings"""
        try:
            config_dir = os.path.join(os.path.expanduser("~"), ".lut_attendance")
            os.makedirs(config_dir, exist_ok=True)
            config_file = os.path.join(config_dir, "window_position.json")

            if os.path.exists(config_file):
                with open(config_file, 'r') as f:
                    position = json.load(f)
                    # Verify the position is still valid for any monitor
                    if self._is_position_on_screen(position.get('x'), position.get('y')):
                        self._root.geometry(f"{position.get('width', 1280)}x{position.get('height', 720)}+{position['x']}+{position['y']}")
        except Exception:
            # Fall back to default if anything goes wrong
            pass

    def _is_position_on_screen(self, x, y):
        """Check if coordinates are visible on any monitor"""
        if x is None or y is None:
            return False

        # Simple check - could be enhanced with actual monitor bounds
        return 0 <= x < 3000 and 0 <= y < 2000  # Reasonable bounds for most setups

    def _handle_window_configure(self, event):
        """Stabilize layout during window moves/resizes"""
        # Only process if it's an actual size/position change
        if hasattr(self, '_last_geometry') and self._last_geometry == self._root.geometry():
            return

        self._last_geometry = self._root.geometry()

        # Force navigation to maintain its state
        if hasattr(self, 'nav_frame') and hasattr(self.nav_frame, 'refresh_layout'):
            self.nav_frame.refresh_layout()

    def _on_close(self):
        """Save window position before closing"""
        try:
            config_dir = os.path.join(os.path.expanduser("~"), ".lut_attendance")
            os.makedirs(config_dir, exist_ok=True)
            config_file = os.path.join(config_dir, "window_position.json")

            # Get current geometry
            geometry = self._root.geometry()
            matches = re.match(r'(\d+)x(\d+)\+(\d+)\+(\d+)', geometry)
            if matches:
                width, height, x, y = map(int, matches.groups())
                with open(config_file, 'w') as f:
                    json.dump({'width': width, 'height': height, 'x': x, 'y': y}, f)
        except Exception:
            pass  # Don't prevent closing if saving fails

        self._root.destroy()

    def run(self) -> None:
        self._root.mainloop()

    def _maximize_window(self) -> None:
        try:
            if os.name == "nt":
                self._root.state("zoomed")
            else:
                self._root.attributes("-zoomed", True)
        except Exception:
            # Ignore platforms that don't support zoomed state
            pass
