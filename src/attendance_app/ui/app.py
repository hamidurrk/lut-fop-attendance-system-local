from __future__ import annotations

import customtkinter as ctk

from attendance_app.config.settings import settings
from attendance_app.data import Database
from attendance_app.services import AttendanceService
from attendance_app.ui.components.collapsible_nav import CollapsibleNav
from attendance_app.ui.navigation import NAV_ITEMS
from attendance_app.ui.placeholders import PlaceholderView
from attendance_app.ui.take_attendance_view import TakeAttendanceView
from attendance_app.ui.theme import VS_BG


class AttendanceApp:
    def __init__(self) -> None:
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

        self._nav = CollapsibleNav(self._root, items=NAV_ITEMS, on_select=self._show_view)
        self._nav.grid(row=0, column=0, sticky="nsw")

        self._content = ctk.CTkFrame(self._root, corner_radius=0, fg_color=VS_BG)
        self._content.grid(row=0, column=1, sticky="nsew")
        self._content.grid_rowconfigure(0, weight=1)
        self._content.grid_columnconfigure(0, weight=1)

        self._views = {
            "take_attendance": TakeAttendanceView(
                self._content,
                self._attendance_service,
                on_session_started=self._handle_session_started,
                on_session_ended=self._handle_session_ended,
            ),
            "history": PlaceholderView(
                self._content,
                title="Attendance history",
                message="Browse historical attendance records here soon.",
            ),
            "auto_grader": PlaceholderView(
                self._content,
                title="Auto-grader",
                message="Automate grading workflows from this tab in future iterations.",
            ),
        }

        for view in self._views.values():
            view.grid(row=0, column=0, sticky="nsew")

        self._show_view("take_attendance")
        self._nav.select("take_attendance")

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

    def run(self) -> None:
        self._root.mainloop()
