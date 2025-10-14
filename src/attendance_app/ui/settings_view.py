from __future__ import annotations

import sys
from pathlib import Path
from tkinter import StringVar
from typing import Any, Callable

import customtkinter as ctk
from customtkinter import filedialog

from attendance_app.config.user_settings_store import DEFAULT_SETTINGS, UserSettingsStore
from attendance_app.ui.theme import (
    VS_ACCENT,
    VS_ACCENT_HOVER,
    VS_BG,
    VS_BORDER,
    VS_DIVIDER,
    VS_SURFACE,
    VS_SURFACE_ALT,
    VS_SUCCESS,
    VS_TEXT,
    VS_TEXT_MUTED,
    VS_WARNING,
)


class SettingsView(ctk.CTkFrame):
    """Interactive settings form backed by the UserSettingsStore."""

    def __init__(
        self,
        master: Any,
        *,
        store: UserSettingsStore,
        on_settings_saved: Callable[[dict[str, Any]], None] | None = None,
        chrome_required: bool = False,
    ) -> None:
        super().__init__(master, fg_color=VS_BG)
        self._store = store
        self._on_settings_saved = on_settings_saved

        self._attendance_points_var = StringVar()
        self._bonus_points_var = StringVar()
        self._chrome_path_var = StringVar()
        self._app_data_dir_var = StringVar()

        self._status_label: ctk.CTkLabel | None = None
        self._chrome_hint_label: ctk.CTkLabel | None = None
        self._chrome_required = chrome_required

        self._build_layout()
        self.refresh()

        if self._chrome_required:
            self.notify_chrome_required()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def refresh(self) -> None:
        """Reload the form inputs from the underlying store."""

        data = self._store.data
        attendance_default = data.get(
            "default_attendance_points", DEFAULT_SETTINGS["default_attendance_points"]
        )
        bonus_default = data.get(
            "default_bonus_points", DEFAULT_SETTINGS["default_bonus_points"]
        )

        self._attendance_points_var.set(str(attendance_default))
        self._bonus_points_var.set(str(bonus_default))

        chrome_path = data.get("chrome_binary_path") or ""
        self._chrome_path_var.set(chrome_path)

        app_data_dir = data.get("app_data_dir", DEFAULT_SETTINGS["app_data_dir"])
        self._app_data_dir_var.set(str(app_data_dir))

        if self._chrome_hint_label is not None:
            self._chrome_hint_label.configure(text_color=VS_TEXT_MUTED)

        self._set_status("")

    def notify_chrome_required(self, message: str | None = None) -> None:
        notice = message or (
            "Chrome couldn't be located automatically. Please set the path to the Chrome executable below."
        )
        self._set_status(notice, tone="warning")
        if self._chrome_hint_label is not None:
            self._chrome_hint_label.configure(text_color=VS_WARNING)

    # ------------------------------------------------------------------
    # Layout helpers
    # ------------------------------------------------------------------
    def _build_layout(self) -> None:
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        container = ctk.CTkFrame(self, fg_color=VS_SURFACE, corner_radius=18)
        container.grid(row=0, column=0, padx=24, pady=24, sticky="nsew")
        container.grid_columnconfigure(0, weight=1)
        container.grid_columnconfigure(1, weight=1)

        title = ctk.CTkLabel(
            container,
            text="Application settings",
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color=VS_TEXT,
        )
        title.grid(row=0, column=0, columnspan=2, sticky="w", padx=28, pady=(28, 8))

        description = ctk.CTkLabel(
            container,
            text=(
                "Customize default grading points, your Chrome installation, and the data folder used to store "
                "attendance information. Changes are saved immediately and apply across the app."
            ),
            justify="left",
            wraplength=640,
            text_color=VS_TEXT_MUTED,
        )
        description.grid(row=1, column=0, columnspan=2, sticky="w", padx=28, pady=(0, 20))

        row_index = 2
        row_index = self._build_number_field(
            container,
            row=row_index,
            label="Default attendance points",
            variable=self._attendance_points_var,
            helper="Used when logging new attendance records.",
        )

        row_index = self._build_number_field(
            container,
            row=row_index,
            label="Default bonus points",
            variable=self._bonus_points_var,
            helper="Auto-filled for new bonus entries and automation results.",
        )

        row_index = self._build_chrome_field(container, row=row_index)
        row_index = self._build_app_data_field(container, row=row_index)

        buttons_row = ctk.CTkFrame(container, fg_color=VS_SURFACE)
        buttons_row.grid(row=row_index, column=0, columnspan=2, sticky="ew", padx=28, pady=(12, 24))
        buttons_row.grid_columnconfigure(0, weight=1)
        buttons_row.grid_columnconfigure(1, weight=0)
        buttons_row.grid_columnconfigure(2, weight=0)

        reset_button = ctk.CTkButton(
            buttons_row,
            text="Reset to defaults",
            width=160,
            text_color=VS_TEXT,
            fg_color=VS_SURFACE_ALT,
            hover_color=VS_DIVIDER,
            command=self._handle_reset,
        )
        reset_button.grid(row=0, column=1, padx=(0, 8))

        save_button = ctk.CTkButton(
            buttons_row,
            text="Save changes",
            width=180,
            text_color=VS_TEXT,
            fg_color=VS_ACCENT,
            hover_color=VS_ACCENT_HOVER,
            command=self._handle_save,
        )
        save_button.grid(row=0, column=2)

        self._status_label = ctk.CTkLabel(
            container,
            text="",
            text_color=VS_TEXT_MUTED,
            wraplength=640,
            justify="left",
        )
        self._status_label.grid(row=row_index + 1, column=0, columnspan=2, sticky="w", padx=28, pady=(0, 12))

    def _build_number_field(
        self,
        parent: ctk.CTkFrame,
        *,
        row: int,
        label: str,
        variable: StringVar,
        helper: str,
    ) -> int:
        parent.grid_rowconfigure(row, weight=0)
        parent.grid_columnconfigure(0, weight=0)
        parent.grid_columnconfigure(1, weight=1)

        field_label = ctk.CTkLabel(parent, text=label, text_color=VS_TEXT, font=ctk.CTkFont(size=18))
        field_label.grid(row=row, column=0, sticky="w", padx=28, pady=(0, 6))

        entry = ctk.CTkEntry(
            parent,
            textvariable=variable,
            width=60,
            fg_color=VS_BG,
            border_color=VS_BORDER,
            text_color=VS_TEXT,
        )
        entry.grid(row=row, column=1, sticky="w", padx=(0, 28), pady=(0, 6))

        helper_label = ctk.CTkLabel(
            parent,
            text=helper,
            text_color=VS_TEXT_MUTED,
            wraplength=480,
            font=ctk.CTkFont(size=14),
        )
        helper_label.grid(row=row + 1, column=0, columnspan=2, sticky="w", padx=28, pady=(0, 14))
        return row + 2

    def _build_chrome_field(self, parent: ctk.CTkFrame, *, row: int) -> int:
        parent.grid_rowconfigure(row, weight=0)

        label = ctk.CTkLabel(parent, text="Chrome binary path", text_color=VS_TEXT, font=ctk.CTkFont(size=18))
        label.grid(row=row, column=0, sticky="w", padx=28, pady=(0, 6))

        field_container = ctk.CTkFrame(parent, fg_color=VS_SURFACE)
        field_container.grid(row=row, column=1, sticky="w", padx=(0, 28), pady=(0, 6))
        field_container.grid_columnconfigure(0, weight=1)
        field_container.grid_columnconfigure(1, weight=0)

        entry = ctk.CTkEntry(
            field_container,
            textvariable=self._chrome_path_var,
            fg_color=VS_BG,
            border_color=VS_BORDER,
            text_color=VS_TEXT,
            width=540
        )
        entry.grid(row=0, column=0, sticky="w", padx=(0, 12))

        browse_button = ctk.CTkButton(
            field_container,
            text="Browse",
            width=100,
            text_color=VS_TEXT,
            fg_color=VS_SURFACE_ALT,
            hover_color=VS_DIVIDER,
            command=self._choose_chrome_path,
        )
        browse_button.grid(row=0, column=1)

        hint = (
            "If left blank, the app will attempt to auto-detect Chrome."
            "On Windows this is typically located at C:/Program Files/Google/Chrome/Application/chrome.exe."
        )
        self._chrome_hint_label = ctk.CTkLabel(
            parent,
            text=hint,
            text_color=VS_TEXT_MUTED,
            wraplength=540,
            font=ctk.CTkFont(size=14),
            justify="left",
        )
        self._chrome_hint_label.grid(row=row + 1, column=0, columnspan=2, sticky="w", padx=28, pady=(0, 14))
        return row + 2

    def _build_app_data_field(self, parent: ctk.CTkFrame, *, row: int) -> int:
        parent.grid_rowconfigure(row, weight=0)

        label = ctk.CTkLabel(parent, text="App data directory", text_color=VS_TEXT, font=ctk.CTkFont(size=18))
        label.grid(row=row, column=0, sticky="w", padx=28, pady=(0, 6))

        field_container = ctk.CTkFrame(parent, fg_color=VS_SURFACE)
        field_container.grid(row=row, column=1, sticky="w", padx=(0, 28), pady=(0, 6))
        field_container.grid_columnconfigure(0, weight=1)
        field_container.grid_columnconfigure(1, weight=0)

        entry = ctk.CTkEntry(
            field_container,
            textvariable=self._app_data_dir_var,
            fg_color=VS_BG,
            border_color=VS_BORDER,
            text_color=VS_TEXT,
            width=540
        )
        entry.grid(row=0, column=0, sticky="w", padx=(0, 12))

        browse_button = ctk.CTkButton(
            field_container,
            text="Browse",
            width=100,
            text_color=VS_TEXT,
            fg_color=VS_SURFACE_ALT,
            hover_color=VS_DIVIDER,
            command=self._choose_app_data_dir,
        )
        browse_button.grid(row=0, column=1, sticky="w")

        helper = (
            "This folder stores the attendance database, Chrome profile, and other generated files. "
            "Choose a location with write permissions."
        )
        helper_label = ctk.CTkLabel(
            parent,
            text=helper,
            text_color=VS_TEXT_MUTED,
            wraplength=540,
            font=ctk.CTkFont(size=14),
            justify="left",
        )
        helper_label.grid(row=row + 1, column=0, columnspan=2, sticky="w", padx=28, pady=(0, 14))
        return row + 2

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def _handle_reset(self) -> None:
        self._attendance_points_var.set(str(DEFAULT_SETTINGS["default_attendance_points"]))
        self._bonus_points_var.set(str(DEFAULT_SETTINGS["default_bonus_points"]))
        self._chrome_path_var.set("")
        self._app_data_dir_var.set(str(DEFAULT_SETTINGS["app_data_dir"]))
        self._set_status("Fields reset. Save to persist the changes.", tone="info")

    def _handle_save(self) -> None:
        errors: list[str] = []

        attendance_points = self._validate_int_field(
            self._attendance_points_var.get(),
            field_name="Default attendance points",
            errors=errors,
        )
        bonus_points = self._validate_int_field(
            self._bonus_points_var.get(),
            field_name="Default bonus points",
            errors=errors,
        )

        chrome_path_value = self._chrome_path_var.get().strip()
        chrome_path: Path | None = None
        if chrome_path_value:
            candidate = Path(chrome_path_value).expanduser()
            if not candidate.exists():
                errors.append("Chrome path does not exist. Please choose a valid executable.")
            else:
                chrome_path = candidate

        app_data_raw = self._app_data_dir_var.get().strip()
        app_data_dir: Path | None = None
        if app_data_raw:
            app_data_candidate = Path(app_data_raw).expanduser()
            try:
                app_data_candidate.mkdir(parents=True, exist_ok=True)
                app_data_dir = app_data_candidate
            except Exception:
                errors.append("Unable to create or access the selected app data directory.")
        else:
            errors.append("App data directory is required.")

        if errors:
            self._set_status("\n".join(errors), tone="warning")
            return

        payload: dict[str, Any] = {}
        if attendance_points is not None:
            payload["default_attendance_points"] = attendance_points
        if bonus_points is not None:
            payload["default_bonus_points"] = bonus_points
        payload["chrome_binary_path"] = str(chrome_path) if chrome_path else None
        payload["app_data_dir"] = str(app_data_dir) if app_data_dir is not None else None

        updated = self._store.update(**payload)
        self.refresh()
        self._set_status("Settings saved successfully.", tone="success")

        if self._on_settings_saved is not None:
            self._on_settings_saved(updated)

    def _validate_int_field(self, raw: str, *, field_name: str, errors: list[str]) -> int | None:
        value = raw.strip()
        if not value:
            errors.append(f"{field_name} is required.")
            return None
        try:
            parsed = int(value)
        except ValueError:
            errors.append(f"{field_name} must be an integer.")
            return None
        if parsed < 0:
            errors.append(f"{field_name} cannot be negative.")
            return None
        return parsed

    def _choose_chrome_path(self) -> None:
        initial_path = self._chrome_path_var.get().strip()
        initial_dir = str(Path(initial_path).expanduser().parent) if initial_path else None
        filetypes = []
        if sys.platform.startswith("win"):
            filetypes = [("Chrome executable", "chrome.exe"), ("Executable", "*.exe")]
        else:
            filetypes = [("Executable", "*")]

        selected = filedialog.askopenfilename(
            title="Select Chrome executable",
            initialdir=initial_dir or None,
            filetypes=filetypes or None,
        )
        if selected:
            self._chrome_path_var.set(str(Path(selected).expanduser()))

    def _choose_app_data_dir(self) -> None:
        initial_dir = self._app_data_dir_var.get().strip() or None
        selected = filedialog.askdirectory(
            title="Select app data directory",
            initialdir=initial_dir or None,
        )
        if selected:
            self._app_data_dir_var.set(str(Path(selected).expanduser()))

    def _set_status(self, message: str, *, tone: str = "info") -> None:
        if self._status_label is None:
            return
        color_map = {
            "info": VS_TEXT_MUTED,
            "success": VS_SUCCESS,
            "warning": VS_WARNING,
        }
        text_color = color_map.get(tone, VS_TEXT_MUTED)
        self._status_label.configure(text=message, text_color=text_color)
