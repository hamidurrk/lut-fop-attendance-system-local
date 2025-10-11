from __future__ import annotations

import json
import os
import re
from typing import cast

import tkinter.messagebox as messagebox
from tkinter import PhotoImage

import customtkinter as ctk
from PIL import Image

from attendance_app.automation import (
    AutoGradingRoutine,
    ChromeRemoteController,
    ChromeAutomationError,
    open_moodle_courses,
    run_auto_grading,
)
from attendance_app.config.settings import settings, refresh_settings_from_store, user_settings_store
from attendance_app.data import Database
from attendance_app.services import AttendanceService
from attendance_app.ui.components.collapsible_nav import CollapsibleNav
from attendance_app.ui.navigation import NAV_ITEMS
from attendance_app.ui.take_attendance_view import TakeAttendanceView
from attendance_app.ui.manage_records_view import ManageRecordsView
from attendance_app.ui.auto_grader_view import AutoGraderView
from attendance_app.ui.settings_view import SettingsView
from attendance_app.ui.theme import VS_BG
from attendance_app.ui.utils import get_asset_path


class AttendanceApp:
    def __init__(self) -> None:
        super().__init__()

        try:
            from ctypes import windll
            windll.shcore.SetProcessDpiAwareness(1)  
        except (ImportError, AttributeError):
            pass  

        ctk.set_appearance_mode("dark")

        self._root = ctk.CTk()
        self._root.title(settings.app_name)
        self._root.geometry("1280x720")
        self._root.minsize(1080, 640)
        self._root.configure(fg_color=VS_BG)

        icon_path = get_asset_path("icon.png")
        self._icon_photo: PhotoImage | None = None
        if icon_path is not None:
            try:
                self._icon_photo = PhotoImage(file=str(icon_path))
                self._root.iconphoto(True, self._icon_photo)

                with Image.open(icon_path) as img:
                    icon_image = img.convert("RGBA")
                    config_dir = os.path.join(os.path.expanduser("~"), ".lut_attendance")
                    os.makedirs(config_dir, exist_ok=True)
                    ico_path = os.path.join(config_dir, "app_icon.ico")
                    icon_image.save(ico_path, format="ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64)])
                    self._root.iconbitmap(default=ico_path)
            except Exception:
                self._icon_photo = None

        self._root.grid_rowconfigure(0, weight=1)
        self._root.grid_columnconfigure(1, weight=1)

        self._database = Database(settings.database_path)
        self._attendance_service = AttendanceService(self._database)
        self._attendance_service.initialize()

        self._chrome_controller: ChromeRemoteController | None = None
        self._chrome_prompt_message: str | None = None
        try:
            self._chrome_controller = ChromeRemoteController()
        except ChromeAutomationError as exc:
            self._chrome_controller = None
            self._chrome_prompt_message = str(exc)
            messagebox.showwarning(
                title="Chrome not found",
                message=f"{self._chrome_prompt_message}\n\nOpen the Settings page to configure the Chrome binary path.",
            )

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
        self._take_attendance_view = take_attendance_view

        auto_grader_view = AutoGraderView(
            self._content,
            self._attendance_service,
            chrome_controller=self._chrome_controller,
            on_detail_open=self._handle_auto_grader_detail_open,
            on_detail_close=self._handle_auto_grader_detail_close,
        )

        self._views = {
            "take_attendance": take_attendance_view,
            "history": ManageRecordsView(
                self._content,
                self._attendance_service,
            ),
            "auto_grader": auto_grader_view,
            "settings": SettingsView(
                self._content,
                store=user_settings_store,
                on_settings_saved=self._handle_settings_saved,
                chrome_required=self._chrome_controller is None,
            ),
        }
        self._settings_view = cast(SettingsView, self._views["settings"])

        self._auto_grader_view = auto_grader_view

        take_attendance_view.register_bonus_automation_handler(open_moodle_courses)
        auto_grader_view.register_grading_handler(run_auto_grading)

        for view in self._views.values():
            view.grid(row=0, column=0, sticky="nsew")

        initial_view = "settings" if self._chrome_prompt_message else "take_attendance"
        self._show_view(initial_view)
        self._nav.select(initial_view)

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
            view = self._views[key]
            view.grid()
            if key == "auto_grader":
                self._auto_grader_view.refresh()
            elif key == "settings":
                self._settings_view.refresh()
                self._handle_auto_grader_detail_close()
            else:
                self._handle_auto_grader_detail_close()

    def register_auto_grading_handler(self, handler: AutoGradingRoutine | None) -> None:
        """Allow external code to override the default automation routine."""
        self._auto_grader_view.register_grading_handler(handler)

    def _handle_settings_saved(self, _updated: dict[str, object]) -> None:
        previous_db_path = getattr(self._database, "_db_path", None)
        previous_controller = self._chrome_controller

        user_settings_store.reload()
        refresh_settings_from_store()

        database_changed = previous_db_path is None or settings.database_path != previous_db_path
        if database_changed:
            self._database = Database(settings.database_path)
            self._attendance_service._database = self._database
            self._attendance_service.initialize()
            self._auto_grader_view.refresh()

        self._take_attendance_view.refresh_user_preferences()

        new_controller: ChromeRemoteController | None = None
        try:
            new_controller = ChromeRemoteController()
        except ChromeAutomationError as exc:
            new_controller = None
            self._chrome_prompt_message = str(exc)
            messagebox.showwarning(
                title="Chrome not found",
                message=f"{exc}\n\nUpdate the Chrome binary path in Settings to enable automation.",
            )
            self._settings_view.notify_chrome_required(str(exc))
        else:
            self._chrome_prompt_message = None

        if previous_controller is not None and previous_controller is not new_controller:
            try:
                previous_controller.shutdown()
            except Exception:
                pass

        self._chrome_controller = new_controller
        self._take_attendance_view.set_chrome_controller(new_controller)
        self._auto_grader_view.set_chrome_controller(new_controller)

    def _handle_session_started(self) -> None:
        self._nav.collapse()
        self._nav.set_navigation_enabled(False)

    def _handle_session_ended(self) -> None:
        self._nav.set_navigation_enabled(True)
        self._nav.expand()
        self._auto_grader_view.refresh()

    def _handle_auto_grader_detail_open(self) -> None:
        self._nav.collapse()

    def _handle_auto_grader_detail_close(self) -> None:
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
