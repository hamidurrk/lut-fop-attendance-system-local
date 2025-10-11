from __future__ import annotations

import csv
import re
from pathlib import Path
from tkinter import filedialog
from typing import Any
from difflib import SequenceMatcher
from openpyxl import Workbook
import customtkinter as ctk
import numpy as np
from scipy.optimize import linear_sum_assignment

from attendance_app.models.attendance import WEEKDAY_LABELS
from attendance_app.services import AttendanceService
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

BONUS_HIGHLIGHT_BG = "#1b2d66"

class ManageRecordsView(ctk.CTkFrame):
    """Interactive management view for past attendance sessions."""

    MATCH_THRESHOLD = 0.62

    def __init__(self, master, attendance_service: AttendanceService) -> None:
        super().__init__(master, fg_color=VS_BG)
        self._service = attendance_service

        self._weekday_var = ctk.StringVar(value="All days")
        self._time_var = ctk.StringVar(value="All times")
        self._status_var = ctk.StringVar(value="Select a session to review attendance history.")

        self._sessions: list[dict[str, Any]] = []
        self._session_rows: list[dict[str, Any]] = []
        self._selected_session: dict[str, Any] | None = None

        self._attendance_records: list[dict[str, Any]] = []
        self._bonus_summary: list[dict[str, Any]] = []

        self._summary_var = ctk.StringVar(value="")

        self._list_container: ctk.CTkFrame | None = None
        self._detail_container: ctk.CTkFrame | None = None

        self._attendance_value_vars: dict[int, ctk.StringVar] = {}
        self._attendance_total_entries: dict[int, ctk.CTkEntry] = {}
        self._attendance_bonus_vars: dict[int, ctk.StringVar] = {}
        self._attendance_bonus_entries: dict[int, ctk.CTkEntry] = {}
        self._initial_totals: dict[int, int] = {}
        self._initial_bonuses: dict[int, int] = {}
        self._invalid_entries: set[int] = set()
        self._unsaved_changes = False
        self._detail_ready = False
        self._suspend_entry_updates: set[int] = set()
        self._requires_bonus_alignment = False
        self._highlight_bonus_var = ctk.BooleanVar(value=False)
        self._attendance_row_frames: dict[int, dict[str, Any]] = {}

        self._filter_title_font = ctk.CTkFont(size=20, weight="bold")
        self._filter_label_font = ctk.CTkFont(size=15)
        self._session_header_font = ctk.CTkFont(size=18, weight="bold")
        self._session_table_header_font = ctk.CTkFont(size=16, weight="bold")
        self._session_table_body_font = ctk.CTkFont(size=15)

        self._build_layout()

        # Populate filter options and initial session list
        sessions = self._load_filter_options()
        self._render_session_cards(sessions)
        self._show_list_view()

    # ------------------------------------------------------------------
    # Layout construction
    # ------------------------------------------------------------------
    def _build_layout(self) -> None:
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        container = ctk.CTkFrame(self, fg_color=VS_SURFACE, corner_radius=16)
        container.grid(row=0, column=0, sticky="nsew", padx=24, pady=24)
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)

        self._list_container = ctk.CTkFrame(container, fg_color=VS_SURFACE_ALT, corner_radius=18)
        self._list_container.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
        self._list_container.grid_rowconfigure(1, weight=1)
        self._list_container.grid_columnconfigure(0, weight=1)

        self._build_filters(self._list_container)
        self._build_session_list(self._list_container)

        self._detail_container = ctk.CTkFrame(container, fg_color=VS_SURFACE_ALT, corner_radius=18)
        self._detail_container.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
        self._detail_container.grid_rowconfigure(2, weight=1)
        self._detail_container.grid_columnconfigure(0, weight=1)
        self._build_details(self._detail_container)
        self._detail_container.grid_remove()

    def _build_filters(self, parent: ctk.CTkFrame) -> None:
        filter_container = ctk.CTkFrame(parent, fg_color="transparent")
        filter_container.grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 12))
        filter_container.grid_columnconfigure(0, weight=0)  
        filter_container.grid_columnconfigure(1, weight=1)  
        filter_container.grid_columnconfigure(2, weight=1)  
        
        filters = ctk.CTkFrame(filter_container, fg_color=VS_SURFACE, corner_radius=14, 
                              border_width=1, border_color=VS_DIVIDER)
        filters.grid(row=0, column=0, padx=0, pady=0)
        filters.grid_columnconfigure((0, 1), weight=1)

        title = ctk.CTkLabel(
            filters,
            text="Filter sessions",
            font=self._filter_title_font,
            text_color=VS_TEXT,
        )
        title.grid(row=0, column=0, columnspan=2, sticky="w", pady=(16, 4), padx=18)

        subtitle = ctk.CTkLabel(
            filters,
            text="Narrow the session list by meeting day or time slot.",
            font=ctk.CTkFont(size=13),
            text_color=VS_TEXT_MUTED,
        )
        subtitle.grid(row=1, column=0, columnspan=2, sticky="w", padx=18, pady=(0, 12))

        weekday_row = ctk.CTkFrame(filters, fg_color="transparent")
        weekday_row.grid(row=2, column=0, columnspan=2, sticky="ew", padx=18, pady=6)
        weekday_row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            weekday_row,
            text="Weekday",
            text_color=VS_TEXT,
            font=self._filter_label_font,
        ).grid(row=0, column=0, sticky="w", padx=(0, 12))

        weekday_values = ["All days", *[label for _, label in sorted(WEEKDAY_LABELS.items())]]
        self._weekday_menu = ctk.CTkOptionMenu(
            weekday_row,
            variable=self._weekday_var,
            values=weekday_values,
            command=lambda *_: self._refresh_session_list(),
            fg_color=VS_SURFACE_ALT,
            button_color=VS_ACCENT,
            button_hover_color=VS_ACCENT_HOVER,
            font=self._filter_label_font,
            dropdown_fg_color=VS_SURFACE,
            dropdown_hover_color=VS_ACCENT,
        )
        self._weekday_menu.grid(row=0, column=1, sticky="ew")

        time_row = ctk.CTkFrame(filters, fg_color="transparent")
        time_row.grid(row=3, column=0, columnspan=2, sticky="ew", padx=18, pady=6)
        time_row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            time_row,
            text="Time", text_color=VS_TEXT,
            font=self._filter_label_font,
        ).grid(row=0, column=0, sticky="w", padx=(0, 12))

        self._time_menu = ctk.CTkOptionMenu(
            time_row,
            variable=self._time_var,
            values=["All times"],
            command=lambda *_: self._refresh_session_list(),
            fg_color=VS_SURFACE_ALT,
            button_color=VS_ACCENT,
            button_hover_color=VS_ACCENT_HOVER,
            font=self._filter_label_font,
            dropdown_fg_color=VS_SURFACE,
            dropdown_hover_color=VS_ACCENT,
        )
        self._time_menu.grid(row=0, column=1, sticky="ew")

        reset_button = ctk.CTkButton(
            filters,
            text="Reset filters",
            command=self._reset_filters,
            fg_color=VS_ACCENT,
            hover_color=VS_ACCENT_HOVER,
            text_color=VS_TEXT,
            font=ctk.CTkFont(size=15, weight="bold"),
            height=44,
        )
        reset_button.grid(row=4, column=0, columnspan=2, sticky="ew", padx=18, pady=(12, 20))

    def _build_session_list(self, parent: ctk.CTkFrame) -> None:
        list_card = ctk.CTkFrame(parent, fg_color=VS_SURFACE, corner_radius=14, border_width=1, border_color=VS_DIVIDER)
        list_card.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 18))
        list_card.grid_rowconfigure(2, weight=1)
        list_card.grid_columnconfigure(0, weight=1)

        header = ctk.CTkLabel(
            list_card,
            text="Sessions",
            font=self._session_header_font,
            text_color=VS_TEXT,
        )
        header.grid(row=0, column=0, sticky="w", padx=18, pady=(18, 8))

        header_row = ctk.CTkFrame(
            list_card,
            fg_color=VS_SURFACE_ALT,
            corner_radius=10,
        )
        header_row.grid(row=1, column=0, sticky="ew", padx=40, pady=(0, 8))

        column_weights = (2, 3, 1, 1, 1)
        for col_index, weight in enumerate(column_weights):
            header_row.grid_columnconfigure(col_index, weight=weight, uniform="session_cols")

        columns = [
            ("Chapter", 0, "w"),
            ("Day & time", 1, "w"),
            ("Status", 2, "center"),
            ("Attendance", 3, "center"),
            ("Bonus", 4, "center"),
        ]
        for text, col, anchor in columns:
            justification = "left" if anchor == "w" else "center"
            ctk.CTkLabel(
                header_row,
                text=text,
                font=self._session_table_header_font,
                text_color=VS_TEXT,
                anchor=anchor,
                justify=justification,
            ).grid(row=0, column=col, sticky="ew", padx=(16 if col == 0 else 12, 12 if col < len(columns) - 1 else 16), pady=8)

        self._session_list = ctk.CTkScrollableFrame(
            list_card,
            fg_color=VS_SURFACE,
            corner_radius=12,
            scrollbar_fg_color=VS_BORDER,
            scrollbar_button_color=VS_ACCENT,
        )
        self._session_list.grid(row=2, column=0, sticky="nsew", padx=(12, 8), pady=(0, 16))
        self._session_list.grid_columnconfigure(0, weight=1)

        self._empty_sessions_label = ctk.CTkLabel(
            self._session_list,
            text="No sessions found for the selected filters.",
            text_color=VS_TEXT_MUTED,
            font=self._session_table_body_font,
        )
        self._empty_sessions_label.grid(row=0, column=0, padx=12, pady=12)

    def _build_details(self, parent: ctk.CTkFrame) -> None:
        parent.grid_rowconfigure(2, weight=1)
        parent.grid_columnconfigure(0, weight=1)

        button_font = ctk.CTkFont(size=15, weight="bold")
        summary_font = ctk.CTkFont(size=16, weight="bold")
        status_font = ctk.CTkFont(size=15)

        top_bar = ctk.CTkFrame(parent, fg_color="transparent")
        top_bar.grid(row=0, column=0, sticky="ew", padx=24, pady=(24, 8))
        top_bar.grid_columnconfigure(0, weight=0)
        top_bar.grid_columnconfigure(1, weight=1)

        back_button = ctk.CTkButton(
            top_bar,
            text="◀ Back",
            command=self._show_list_view,
            width=110,
            height=46,
            fg_color=VS_SURFACE,
            hover_color=VS_SURFACE_ALT,
            border_width=1,
            border_color=VS_DIVIDER,
            text_color=VS_TEXT,
            font=button_font,
        )
        back_button.grid(row=0, column=0, rowspan=2, padx=(0, 16), sticky="n")

        self._session_title = ctk.CTkLabel(
            top_bar,
            text="Session details",
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color=VS_TEXT,
            anchor="w",
            justify="left",
        )
        self._session_title.grid(row=0, column=1, sticky="w")

        self._session_metadata_label = ctk.CTkLabel(
            top_bar,
            text="",
            font=ctk.CTkFont(size=16),
            text_color=VS_TEXT_MUTED,
            anchor="w",
            justify="left",
        )
        self._session_metadata_label.grid(row=1, column=1, sticky="w", pady=(4, 0))

        status_row = ctk.CTkFrame(parent, fg_color="transparent")
        status_row.grid(row=1, column=0, sticky="ew", padx=24, pady=(0, 12))
        status_row.grid_columnconfigure(0, weight=1)
        status_row.grid_columnconfigure(1, weight=0)

        status_text = ctk.CTkFrame(status_row, fg_color="transparent")
        status_text.grid(row=0, column=0, sticky="w")
        status_text.grid_columnconfigure(0, weight=1)

        self._summary_label = ctk.CTkLabel(
            status_text,
            textvariable=self._summary_var,
            text_color=VS_TEXT,
            justify="left",
            font=summary_font,
            anchor="w",
        )
        self._summary_label.grid(row=0, column=0, sticky="w")

        self._status_label = ctk.CTkLabel(
            status_text,
            textvariable=self._status_var,
            text_color=VS_TEXT_MUTED,
            justify="left",
            font=status_font,
            anchor="w",
        )
        self._status_label.grid(row=1, column=0, sticky="w", pady=(4, 0))

        actions = ctk.CTkFrame(status_row, fg_color="transparent")
        actions.grid(row=0, column=1, sticky="e")
        for index in range(5):
            actions.grid_columnconfigure(index, weight=1)

        self._refresh_button = ctk.CTkButton(
            actions,
            text="Refresh",
            command=self._refresh_current_session,
            fg_color=VS_SURFACE,
            hover_color=VS_SURFACE_ALT,
            border_width=1,
            border_color=VS_DIVIDER,
            text_color=VS_TEXT,
            font=button_font,
            height=46,
            width=120,
        )
        self._refresh_button.grid(row=0, column=0, padx=4)

        self._match_button = ctk.CTkButton(
            actions,
            text="Auto-match bonus",
            command=self._auto_match_bonus,
            fg_color=VS_ACCENT,
            hover_color=VS_ACCENT_HOVER,
            text_color=VS_TEXT,
            font=button_font,
            height=46,
            width=160,
        )
        self._match_button.grid(row=0, column=1, padx=4)

        self._save_button = ctk.CTkButton(
            actions,
            text="Save totals",
            command=self._save_totals,
            fg_color=VS_ACCENT,
            hover_color=VS_ACCENT_HOVER,
            text_color=VS_TEXT,
            font=button_font,
            height=46,
            width=140,
        )
        self._save_button.grid(row=0, column=2, padx=4)

        self._export_csv_button = ctk.CTkButton(
            actions,
            text="Export CSV",
            command=self._export_csv,
            fg_color=VS_SURFACE,
            hover_color=VS_SURFACE_ALT,
            border_width=1,
            border_color=VS_DIVIDER,
            text_color=VS_TEXT,
            font=button_font,
            height=46,
            width=150,
        )
        self._export_csv_button.grid(row=0, column=3, padx=4)

        self._export_excel_button = ctk.CTkButton(
            actions,
            text="Export Excel",
            command=self._export_excel,
            fg_color=VS_SURFACE,
            hover_color=VS_SURFACE_ALT,
            border_width=1,
            border_color=VS_DIVIDER,
            text_color=VS_TEXT,
            font=button_font,
            height=46,
            width=150,
        )
        self._export_excel_button.grid(row=0, column=4, padx=4)

        tables_row = ctk.CTkFrame(parent, fg_color="transparent")
        tables_row.grid(row=2, column=0, sticky="nsew", padx=24, pady=(12, 24))
        tables_row.grid_columnconfigure(0, weight=1)
        tables_row.grid_columnconfigure(1, weight=1)
        tables_row.grid_rowconfigure(0, weight=1)

        self._numeric_entry_width = 80
        self._student_name_column_width = 450
        self._student_id_column_width = 200

        card_title_font = ctk.CTkFont(size=19, weight="bold")
        header_font = ctk.CTkFont(size=17, weight="bold")

        attendance_card = ctk.CTkFrame(
            tables_row,
            fg_color=VS_SURFACE,
            corner_radius=14,
            border_width=1,
            border_color=VS_DIVIDER,
        )
        attendance_card.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        attendance_card.grid_rowconfigure(2, weight=1)
        attendance_card.grid_columnconfigure(0, weight=1)

        attendance_title_row = ctk.CTkFrame(attendance_card, fg_color="transparent")
        attendance_title_row.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
        attendance_title_row.grid_columnconfigure(0, weight=1)
        attendance_title_row.grid_columnconfigure(1, weight=0)

        ctk.CTkLabel(
            attendance_title_row,
            text="Attendance details",
            font=card_title_font,
            text_color=VS_TEXT,
            anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=30)

        self._highlight_bonus_switch = ctk.CTkSwitch(
            attendance_title_row,
            text="Highlight bonus pts > 0",
            variable=self._highlight_bonus_var,
            command=self._on_bonus_highlight_toggle,
            fg_color="#969696",
            progress_color=VS_ACCENT,
            button_color=VS_TEXT,
            button_hover_color="#ffffff",
            text_color=VS_TEXT,
            font=ctk.CTkFont(size=15),
        )
        self._highlight_bonus_switch.grid(row=0, column=1, sticky="e", padx=30)

        attendance_header = ctk.CTkFrame(
            attendance_card,
            fg_color=VS_SURFACE_ALT,
            corner_radius=10,
        )
        attendance_header.grid(row=1, column=0, sticky="ew", padx=30, pady=(0, 6))
        attendance_header.grid_columnconfigure(0, weight=0, minsize=self._student_name_column_width)
        attendance_header.grid_columnconfigure(1, weight=0, minsize=self._student_id_column_width)
        attendance_header.grid_columnconfigure(2, weight=0, minsize=self._numeric_entry_width, uniform="numeric")
        attendance_header.grid_columnconfigure(3, weight=0, minsize=self._numeric_entry_width, uniform="numeric")

        ctk.CTkLabel(
            attendance_header,
            text="Student name",
            font=header_font,
            text_color=VS_TEXT,
            anchor="w",
            wraplength=self._student_name_column_width,
            justify="left",
        ).grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        ctk.CTkLabel(
            attendance_header,
            text="Student ID",
            font=header_font,
            text_color=VS_TEXT,
            anchor="center",
            justify="center",
            wraplength=self._student_id_column_width,
        ).grid(row=0, column=1, sticky="nsew", padx=0, pady=8)
        ctk.CTkLabel(
            attendance_header,
            text="Bonus pts",
            font=header_font,
            text_color=VS_TEXT,
            anchor="e",
            justify="right",
            width=self._numeric_entry_width,
        ).grid(row=0, column=2, sticky="w", padx=(0, 12), pady=8)
        ctk.CTkLabel(
            attendance_header,
            text="Total pts",
            font=header_font,
            text_color=VS_TEXT,
            anchor="e",
            justify="right",
            width=self._numeric_entry_width,
        ).grid(row=0, column=3, sticky="e", padx=(8, 12), pady=8)

        self._attendance_table = ctk.CTkScrollableFrame(
            attendance_card,
            fg_color=VS_SURFACE,
            corner_radius=12,
            scrollbar_fg_color=VS_BORDER,
            scrollbar_button_color=VS_ACCENT,
        )
        self._attendance_table.grid(row=2, column=0, sticky="nsew", padx=12, pady=(0, 12))
        self._attendance_table.grid_columnconfigure(0, weight=1)
        self._attendance_table.grid_rowconfigure(0, weight=1)

        bonus_card = ctk.CTkFrame(
            tables_row,
            fg_color=VS_SURFACE,
            corner_radius=14,
            border_width=1,
            border_color=VS_DIVIDER,
        )
        bonus_card.grid(row=0, column=1, sticky="nsew", padx=(12, 0))
        bonus_card.grid_rowconfigure(2, weight=1)
        bonus_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            bonus_card,
            text="Bonus allocations",
            font=card_title_font,
            text_color=VS_TEXT,
            anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(12, 4))

        bonus_header = ctk.CTkFrame(
            bonus_card,
            fg_color=VS_SURFACE_ALT,
            corner_radius=10,
        )
        bonus_header.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 6))
        bonus_header.grid_columnconfigure(0, weight=3)
        bonus_header.grid_columnconfigure(1, weight=0, minsize=self._numeric_entry_width, uniform="numeric")

        ctk.CTkLabel(
            bonus_header,
            text="Student name",
            font=header_font,
            text_color=VS_TEXT,
            anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=(12, 8), pady=8)
        ctk.CTkLabel(
            bonus_header,
            text="Bonus pts",
            font=header_font,
            text_color=VS_TEXT,
            anchor="e",
            justify="right",
            width=self._numeric_entry_width,
        ).grid(row=0, column=1, sticky="e", padx=(4, 12), pady=8)

        self._bonus_table = ctk.CTkScrollableFrame(
            bonus_card,
            fg_color=VS_SURFACE,
            corner_radius=12,
            scrollbar_fg_color=VS_BORDER,
            scrollbar_button_color=VS_ACCENT,
        )
        self._bonus_table.grid(row=2, column=0, sticky="nsew", padx=12, pady=(0, 12))
        self._bonus_table.grid_columnconfigure(0, weight=1)
        self._bonus_table.grid_rowconfigure(0, weight=1)

        self._toggle_action_buttons(enabled=False)

    # ------------------------------------------------------------------
    # Session loading and filtering
    # ------------------------------------------------------------------
    def _load_filter_options(self) -> list[dict[str, Any]]:
        sessions = self._service.list_sessions()
        hour_ranges = sorted(
            {
                self._format_hour_range(session["start_hour"], session["end_hour"])
                for session in sessions
            }
        )
        hour_values = ["All times", *hour_ranges]
        self._time_menu.configure(values=hour_values)
        if self._time_var.get() not in hour_values:
            self._time_var.set("All times")
        return sessions

    def _refresh_session_list(self) -> None:
        filters: dict[str, Any] = {}

        weekday_choice = self._weekday_var.get()
        if weekday_choice != "All days":
            for index, label in WEEKDAY_LABELS.items():
                if label == weekday_choice:
                    filters["weekday_index"] = index
                    break

        time_choice = self._time_var.get()
        if time_choice != "All times":
            start_hour, end_hour = self._parse_hour_range(time_choice)
            if start_hour is not None and end_hour is not None:
                filters["start_hour"] = start_hour
                filters["end_hour"] = end_hour

        sessions = self._service.list_sessions(**filters)
        self._render_session_cards(sessions)

    def _reset_filters(self) -> None:
        self._weekday_var.set("All days")
        self._time_var.set("All times")
        self._refresh_session_list()

    # ------------------------------------------------------------------
    # Session cards
    # ------------------------------------------------------------------
    def _render_session_cards(self, sessions: list[dict[str, Any]]) -> None:
        for row_info in self._session_rows:
            row_info["frame"].destroy()
        self._session_rows.clear()

        self._sessions = sessions

        if self._selected_session and all(item["id"] != self._selected_session["id"] for item in sessions):
            self._clear_session_selection()

        if not sessions:
            self._empty_sessions_label.grid()
            return

        self._empty_sessions_label.grid_remove()

        day_lookup = WEEKDAY_LABELS

        column_weights = (2, 3, 1, 1, 1)

        for index, session in enumerate(sessions):
            row_frame = ctk.CTkFrame(
                self._session_list,
                fg_color=VS_SURFACE_ALT,
                corner_radius=12,
                border_width=1,
                border_color=VS_DIVIDER,
            )
            row_frame.grid(row=index, column=0, sticky="ew", padx=16, pady=5)
            for col_index, weight in enumerate(column_weights):
                row_frame.grid_columnconfigure(col_index, weight=weight, uniform="session_cols")

            chapter = session.get("chapter_code") or "—"
            weekday_label = day_lookup.get(session.get("weekday_index"), "Day ?")
            start_hour = session.get("start_hour")
            end_hour = session.get("end_hour")
            if start_hour is None or end_hour is None:
                time_range = "—"
            else:
                time_range = self._format_hour_range(int(start_hour), int(end_hour))
            schedule = f"{weekday_label} · {time_range}"
            attendance_summary = f"{session.get('attendance_count', 0)}"
            bonus_summary = f"{session.get('bonus_count', 0)}"
            status_raw = (session.get("status") or "draft").strip().lower()
            status_display = status_raw.replace("_", " ").title()
            status_color_map = {
                "graded": VS_SUCCESS,
                "confirmed": VS_ACCENT,
                "pending": VS_TEXT_MUTED,
            }
            status_color = status_color_map.get(status_raw, VS_TEXT)

            values = [
                (chapter, 0, "w", VS_TEXT),
                (schedule, 1, "w", VS_TEXT),
                (status_display, 2, "center", status_color),
                (attendance_summary, 3, "center", VS_TEXT_MUTED),
                (bonus_summary, 4, "center", VS_TEXT_MUTED),
            ]

            row_info: dict[str, Any] = {
                "frame": row_frame,
                "labels": [],
                "default_colors": [],
                "session_id": session.get("id"),
                "hovered": False,
            }

            for text, column, anchor, color in values:
                justification = "left" if anchor == "w" else "center"
                label = ctk.CTkLabel(
                    row_frame,
                    text=text,
                    font=self._session_table_body_font,
                    text_color=color,
                    anchor=anchor,
                    justify=justification,
                )
                label.grid(
                    row=0,
                    column=column,
                    sticky="ew",
                    padx=(16 if column == 0 else 12, 12 if column < len(values) - 1 else 16),
                    pady=10,
                )
                label.bind("<Button-1>", lambda _event, s=session: self._handle_session_select(s))
                label.bind("<Enter>", lambda _event, info=row_info: self._on_session_row_enter(info))
                label.bind("<Leave>", lambda event, info=row_info: self._on_session_row_leave(info, event))
                row_info["labels"].append(label)
                row_info["default_colors"].append(color)

            row_frame.bind("<Button-1>", lambda _event, s=session: self._handle_session_select(s))
            row_frame.bind("<Enter>", lambda _event, info=row_info: self._on_session_row_enter(info))
            row_frame.bind("<Leave>", lambda event, info=row_info: self._on_session_row_leave(info, event))
            row_frame.configure(cursor="hand2")

            self._session_rows.append(row_info)

        self._highlight_selected_session()

    def _highlight_selected_session(self) -> None:
        selected_id = self._selected_session["id"] if self._selected_session else None
        for row_info, session in zip(self._session_rows, self._sessions):
            is_selected = selected_id is not None and session["id"] == selected_id
            is_hovered = row_info.get("hovered", False) if not is_selected else False
            self._set_session_row_state(row_info, selected=is_selected, hovered=is_hovered)

    def _set_session_row_state(self, row_info: dict[str, Any], *, selected: bool, hovered: bool) -> None:
        frame: ctk.CTkFrame = row_info["frame"]
        labels: list[ctk.CTkLabel] = row_info["labels"]
        default_colors: list[str] = row_info["default_colors"]

        if selected:
            row_info["hovered"] = False
            frame.configure(fg_color=VS_ACCENT, border_color=VS_ACCENT)
            for label in labels:
                label.configure(text_color=VS_TEXT)
            return

        row_info["hovered"] = hovered
        if hovered:
            frame.configure(fg_color=VS_SURFACE, border_color=VS_ACCENT)
            for label in labels:
                label.configure(text_color=VS_TEXT)
        else:
            frame.configure(fg_color=VS_SURFACE_ALT, border_color=VS_DIVIDER)
            for label, color in zip(labels, default_colors):
                label.configure(text_color=color)

    def _on_session_row_enter(self, row_info: dict[str, Any]) -> None:
        session_id = row_info.get("session_id")
        if self._selected_session and session_id == self._selected_session["id"]:
            return
        if row_info.get("hovered"):
            return
        self._set_session_row_state(row_info, selected=False, hovered=True)

    def _on_session_row_leave(self, row_info: dict[str, Any], event: Any) -> None:
        frame: ctk.CTkFrame = row_info["frame"]
        if not frame.winfo_exists():  # pragma: no cover - defensive guard during teardown
            return

        widget = frame.winfo_containing(event.x_root, event.y_root)
        if widget is not None and self._widget_belongs_to_row(widget, frame):
            return

        session_id = row_info.get("session_id")
        is_selected = self._selected_session and session_id == self._selected_session["id"]
        self._set_session_row_state(row_info, selected=bool(is_selected), hovered=False)

    def _widget_belongs_to_row(self, widget: Any, row_frame: ctk.CTkFrame) -> bool:
        current = widget
        while current is not None:
            if current == row_frame:
                return True
            current = getattr(current, "master", None)
        return False

    def _handle_session_select(self, session: dict[str, Any]) -> None:
        self._selected_session = session
        self._highlight_selected_session()
        self._load_session_details(session["id"])

    def _show_list_view(self) -> None:
        if self._detail_container is not None:
            self._detail_container.grid_remove()
        if self._list_container is not None:
            self._list_container.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
        self._selected_session = None
        self._update_session_header()
        self._highlight_selected_session()
        self._summary_var.set("")
        self._set_status("Select a session to review attendance history.")
        self._invalid_entries.clear()
        self._requires_bonus_alignment = False
        self._set_unsaved_changes(False)
        self._toggle_action_buttons(enabled=False)

    def _show_detail_view(self) -> None:
        if self._list_container is not None:
            self._list_container.grid_remove()
        if self._detail_container is not None:
            self._detail_container.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)

    def _clear_session_selection(self) -> None:
        self._selected_session = None
        self._attendance_records = []
        self._bonus_summary = []
        self._attendance_value_vars.clear()
        self._attendance_total_entries.clear()
        self._attendance_bonus_vars.clear()
        self._attendance_bonus_entries.clear()
        self._initial_totals.clear()
        self._initial_bonuses.clear()
        self._attendance_row_frames.clear()
        self._update_session_header()
        self._summary_var.set("")
        self._show_list_view()

    def _update_session_header(self) -> None:
        if not hasattr(self, "_session_title") or not hasattr(self, "_session_metadata_label"):
            return

        session = self._selected_session or {}
        if not session:
            self._session_title.configure(text="Session details")
            self._session_metadata_label.configure(text="")
            return

        chapter = session.get("chapter_code")
        weekday_index = session.get("weekday_index")
        start_hour = session.get("start_hour")
        end_hour = session.get("end_hour")
        campus = session.get("campus_name")

        chapter_display = chapter or "—"
        weekday_label = WEEKDAY_LABELS.get(weekday_index, "—")
        if start_hour is not None and end_hour is not None:
            time_display = self._format_hour_range(int(start_hour), int(end_hour))
        else:
            time_display = "—"
        campus_display = campus or "—"

        if chapter:
            title_text = f"{weekday_label} · {time_display} · C{chapter_display}"
        else:
            title_text = "Session details"

        metadata_parts = [
            f"Chapter {chapter_display}",
            campus_display,
        ]
        metadata_text = " · ".join(metadata_parts)

        self._session_title.configure(text=title_text)
        self._session_metadata_label.configure(text=metadata_text)

    # ------------------------------------------------------------------
    # Session detail handling
    # ------------------------------------------------------------------
    def _load_session_details(self, session_id: int) -> None:
        try:
            attendance_rows = self._service.get_session_attendance(session_id)
            bonus_rows = self._service.get_session_bonus_summary(session_id)
        except Exception as exc:  # pragma: no cover - defensive UI handler
            self._set_status(f"Failed to load session details: {exc}", tone="warning")
            return

        self._attendance_records = [dict(row) for row in attendance_rows]
        self._bonus_summary = [dict(row) for row in bonus_rows]

        self._attendance_value_vars.clear()
        self._attendance_total_entries.clear()
        self._attendance_bonus_vars.clear()
        self._attendance_bonus_entries.clear()
        self._initial_totals.clear()
        self._initial_bonuses.clear()
        self._invalid_entries.clear()
        self._suspend_entry_updates.clear()

        self._update_session_header()

        for record in self._attendance_records:
            record_id = int(record.get("id"))
            a_value = int(record.get("a_point", 0) or 0)
            b_value = int(record.get("b_point", 0) or 0)
            total_value_raw = record.get("t_point")
            if total_value_raw is None:
                total_value = a_value + b_value
            else:
                total_value = int(total_value_raw or 0)

            record["a_point"] = a_value
            record["b_point"] = b_value
            record["t_point"] = total_value

            self._invalid_entries.discard(record_id)
            self._mark_entry_invalid(record_id, False, target="both")

        self._show_detail_view()
        self._populate_attendance_table()
        self._populate_bonus_table()
        self._update_summary()
        self._update_export_requirements()
        self._set_status("Session data loaded.", tone="info")
        self._toggle_action_buttons(enabled=True)
        self._set_unsaved_changes(False)

    def _refresh_current_session(self) -> None:
        if not self._selected_session:
            self._set_status("Choose a session to refresh its data.", tone="warning")
            return
        self._load_session_details(self._selected_session["id"])

    # ------------------------------------------------------------------
    # Attendance and bonus tables
    # ------------------------------------------------------------------
    def _populate_attendance_table(self) -> None:
        if not hasattr(self, "_attendance_table") or self._attendance_table is None:
            return

        for child in self._attendance_table.winfo_children():
            child.destroy()

        self._attendance_value_vars.clear()
        self._attendance_total_entries.clear()
        self._attendance_bonus_vars.clear()
        self._attendance_bonus_entries.clear()
        self._attendance_row_frames.clear()

        if not self._attendance_records:
            ctk.CTkLabel(
                self._attendance_table,
                text="No attendance records captured for this session.",
                text_color=VS_TEXT_MUTED,
                anchor="w",
            ).grid(row=0, column=0, sticky="ew", padx=8, pady=8)
            return

        numeric_width = getattr(self, "_numeric_entry_width", 60)
        name_width = getattr(self, "_student_name_column_width", 240)
        id_width = getattr(self, "_student_id_column_width", 150)
        label_font = ctk.CTkFont(size=16)
        entry_font = ctk.CTkFont(size=16)

        for index, record in enumerate(self._attendance_records):
            row_color = VS_SURFACE if index % 2 == 0 else VS_SURFACE_ALT
            row = ctk.CTkFrame(self._attendance_table, fg_color=row_color, corner_radius=8)
            row.grid(row=index, column=0, sticky="ew", padx=4, pady=2)
            row.grid_columnconfigure(0, weight=0, minsize=name_width)
            row.grid_columnconfigure(1, weight=0, minsize=id_width)
            row.grid_columnconfigure(2, weight=0, minsize=numeric_width, uniform="numeric")
            row.grid_columnconfigure(3, weight=0, minsize=numeric_width, uniform="numeric")
            row.grid_rowconfigure(0, weight=1)

            name = record.get("student_name") or record.get("student_id") or "—"
            student_id = record.get("student_id") or "—"
            bonus_points = int(record.get("b_point", 0) or 0)
            total_points = int(record.get("t_point", 0) or 0)
            record_id = int(record.get("id"))

            name_label = ctk.CTkLabel(
                row,
                text=name,
                text_color=VS_TEXT,
                anchor="w",
                font=label_font,
                wraplength=name_width,
                justify="left",
            )
            name_label.grid(row=0, column=0, sticky="nsew", padx=(12, 8), pady=6)

            id_label = ctk.CTkLabel(
                row,
                text=student_id,
                text_color=VS_TEXT_MUTED,
                anchor="center",
                justify="center",
                wraplength=id_width,
                font=label_font,
            )
            id_label.grid(row=0, column=1, sticky="nsew", padx=8, pady=6)

            bonus_var = ctk.StringVar(value=str(bonus_points))
            bonus_entry = ctk.CTkEntry(
                row,
                textvariable=bonus_var,
                justify="right",
                width=numeric_width,
                fg_color=VS_BG,
                border_color=VS_DIVIDER,
                text_color=VS_TEXT,
                font=entry_font,
            )
            bonus_entry.grid(row=0, column=2, sticky="e", padx=(10, 20), pady=6)

            total_var = ctk.StringVar(value=str(total_points))
            total_entry = ctk.CTkEntry(
                row,
                textvariable=total_var,
                justify="right",
                width=numeric_width,
                fg_color=VS_BG,
                border_color=VS_DIVIDER,
                text_color=VS_TEXT,
                font=entry_font,
            )
            total_entry.grid(row=0, column=3, sticky="e", padx=(4, 20), pady=6)

            bonus_var.trace_add(
                "write", lambda *_args, rid=record_id: self._handle_bonus_entry_change(rid)
            )
            total_var.trace_add(
                "write", lambda *_args, rid=record_id: self._handle_total_entry_change(rid)
            )

            self._attendance_bonus_vars[record_id] = bonus_var
            self._attendance_bonus_entries[record_id] = bonus_entry
            self._attendance_value_vars[record_id] = total_var
            self._attendance_total_entries[record_id] = total_entry

            self._attendance_row_frames[record_id] = {
                "frame": row,
                "default_fg": row_color,
                "labels": {
                    "name": name_label,
                    "id": id_label,
                },
                "id_default_color": VS_TEXT_MUTED,
            }

        self._refresh_bonus_highlights()

    def _on_bonus_highlight_toggle(self) -> None:
        self._refresh_bonus_highlights()

    def _refresh_bonus_highlights(self) -> None:
        highlight_enabled = bool(self._highlight_bonus_var.get()) if hasattr(self, "_highlight_bonus_var") else False

        for record in self._attendance_records:
            record_id = int(record.get("id"))
            info = self._attendance_row_frames.get(record_id)
            if not info:
                continue

            frame: ctk.CTkFrame = info["frame"]
            labels: dict[str, ctk.CTkLabel] = info["labels"]
            default_fg = info["default_fg"]
            id_default_color = info["id_default_color"]
            has_bonus = int(record.get("b_point", 0) or 0) > 0

            if highlight_enabled and has_bonus:
                frame.configure(fg_color=BONUS_HIGHLIGHT_BG)
                labels["name"].configure(text_color=VS_TEXT)
                labels["id"].configure(text_color=VS_TEXT)
            else:
                frame.configure(fg_color=default_fg)
                labels["name"].configure(text_color=VS_TEXT)
                labels["id"].configure(text_color=id_default_color)

    def _populate_bonus_table(self) -> None:
        if not hasattr(self, "_bonus_table") or self._bonus_table is None:
            return

        for child in self._bonus_table.winfo_children():
            child.destroy()

        if not self._bonus_summary:
            ctk.CTkLabel(
                self._bonus_table,
                text="No bonus records for this session.",
                text_color=VS_TEXT_MUTED,
                anchor="w",
            ).grid(row=0, column=0, sticky="ew", padx=8, pady=8)
            return

        numeric_width = getattr(self, "_numeric_entry_width", 60)
        label_font = ctk.CTkFont(size=16)
        value_font = ctk.CTkFont(size=16)

        for index, entry in enumerate(self._bonus_summary):
            row_color = VS_SURFACE if index % 2 == 0 else VS_SURFACE_ALT
            row = ctk.CTkFrame(self._bonus_table, fg_color=row_color, corner_radius=8)
            row.grid(row=index, column=0, sticky="ew", padx=4, pady=2)
            row.grid_columnconfigure(0, weight=3)
            row.grid_columnconfigure(1, weight=0, minsize=numeric_width, uniform="numeric")

            name = entry.get("student_name") or "Unnamed"
            total_bonus = int(entry.get("total_bonus", 0) or 0)

            ctk.CTkLabel(
                row,
                text=name,
                text_color=VS_TEXT,
                anchor="w",
                font=label_font,
            ).grid(row=0, column=0, sticky="ew", padx=(12, 8), pady=6)
            ctk.CTkLabel(
                row,
                text=str(total_bonus),
                text_color=VS_TEXT,
                anchor="e",
                font=value_font,
                width=numeric_width,
            ).grid(row=0, column=1, sticky="e", padx=(4, 12), pady=6)

    def _handle_bonus_entry_change(self, record_id: int) -> None:
        if record_id in self._suspend_entry_updates:
            return

        var = self._attendance_bonus_vars.get(record_id)
        if var is None:
            return

        text = var.get().strip()
        if not text:
            freshly_invalid = record_id not in self._invalid_entries
            self._invalid_entries.add(record_id)
            self._mark_entry_invalid(record_id, True, target="bonus")
            self._update_save_button_state()
            if freshly_invalid:
                self._set_status("Enter whole-number bonus points before saving.", tone="warning")
            return

        try:
            value = int(text)
        except ValueError:
            freshly_invalid = record_id not in self._invalid_entries
            self._invalid_entries.add(record_id)
            self._mark_entry_invalid(record_id, True, target="bonus")
            self._update_save_button_state()
            if freshly_invalid:
                self._set_status("Enter whole-number bonus points before saving.", tone="warning")
            return

        if value < 0:
            value = 0
            self._suspend_entry_updates.add(record_id)
            try:
                var.set("0")
            finally:
                self._suspend_entry_updates.discard(record_id)

        record = self._find_attendance_record(record_id)
        if record is None:
            return

        prev_bonus = int(record.get("b_point", 0) or 0)
        prev_total = int(record.get("t_point", 0) or 0)
        a_value = int(record.get("a_point", 0) or 0)

        new_bonus = value
        new_total = a_value + new_bonus

        record["b_point"] = new_bonus
        record["t_point"] = new_total

        self._invalid_entries.discard(record_id)
        self._mark_entry_invalid(record_id, False, target="bonus")

        self._suspend_entry_updates.add(record_id)
        try:
            total_var = self._attendance_value_vars.get(record_id)
            if total_var is not None:
                total_var.set(str(new_total))
        finally:
            self._suspend_entry_updates.discard(record_id)

        was_unsaved = self._unsaved_changes
        changed = not (new_bonus == prev_bonus and new_total == prev_total)

        if changed:
            self._set_unsaved_changes(True)
            if not was_unsaved:
                self._set_status("Totals updated. Save to persist changes.", tone="info")
        else:
            self._update_save_button_state()
            self._update_export_state()

        self._update_export_requirements()
        self._update_summary()
        self._refresh_bonus_highlights()

    def _handle_total_entry_change(self, record_id: int) -> None:
        if record_id in self._suspend_entry_updates:
            return

        var = self._attendance_value_vars.get(record_id)
        if var is None:
            return

        text = var.get().strip()
        if not text:
            newly_invalid = record_id not in self._invalid_entries
            self._invalid_entries.add(record_id)
            self._mark_entry_invalid(record_id, True, target="total")
            self._update_save_button_state()
            if newly_invalid:
                self._set_status("Enter whole-number totals before saving.", tone="warning")
            return

        try:
            value = int(text)
        except ValueError:
            newly_invalid = record_id not in self._invalid_entries
            self._invalid_entries.add(record_id)
            self._mark_entry_invalid(record_id, True, target="total")
            self._update_save_button_state()
            if newly_invalid:
                self._set_status("Enter whole-number totals before saving.", tone="warning")
            return

        record = self._find_attendance_record(record_id)
        if record is None:
            return

        prev_total = int(record.get("t_point", 0) or 0)
        prev_bonus = int(record.get("b_point", 0) or 0)
        a_value = int(record.get("a_point", 0) or 0)

        new_total = value
        new_bonus = max(0, new_total - a_value)

        record["t_point"] = new_total
        record["b_point"] = new_bonus

        self._suspend_entry_updates.add(record_id)
        try:
            bonus_var = self._attendance_bonus_vars.get(record_id)
            if bonus_var is not None:
                bonus_var.set(str(new_bonus))
        finally:
            self._suspend_entry_updates.discard(record_id)

        self._invalid_entries.discard(record_id)
        self._mark_entry_invalid(record_id, False, target="both")

        was_unsaved = self._unsaved_changes

        changed = not (new_total == prev_total and new_bonus == prev_bonus)

        if changed:
            self._set_unsaved_changes(True)
            if not was_unsaved:
                self._set_status("Totals updated. Save to persist changes.", tone="info")
        else:
            self._update_save_button_state()
            self._update_export_state()

        self._update_export_requirements()
        self._update_summary()

    def _mark_entry_invalid(self, record_id: int, invalid: bool, *, target: str = "both") -> None:
        border_color = VS_WARNING if invalid else VS_DIVIDER

        if target in ("total", "both"):
            total_entry = self._attendance_total_entries.get(record_id)
            if total_entry is not None:
                total_entry.configure(border_color=border_color)

        if target in ("bonus", "both"):
            bonus_entry = getattr(self, "_attendance_bonus_entries", {}).get(record_id)
            if bonus_entry is not None:
                bonus_entry.configure(border_color=border_color)

    def _find_attendance_record(self, record_id: int) -> dict[str, Any] | None:
        for record in self._attendance_records:
            if int(record.get("id")) == record_id:
                return record
        return None

    def _auto_match_bonus(self) -> None:
        if not self._selected_session:
            self._set_status("Select a session before running auto-match.", tone="warning")
            return

        if not self._attendance_records:
            self._set_status("No attendance records available for matching.", tone="warning")
            return

        if not self._bonus_summary:
            self._set_status("No bonus entries to match.", tone="info")
            return

        bonus_count = len(self._bonus_summary)
        attendance_count = len(self._attendance_records)
        if bonus_count == 0 or attendance_count == 0:
            self._set_status("Nothing to match.", tone="info")
            return

        matrix = np.zeros((bonus_count, attendance_count), dtype=float)
        for row_index, bonus_entry in enumerate(self._bonus_summary):
            for col_index, attendance_entry in enumerate(self._attendance_records):
                matrix[row_index, col_index] = self._compute_match_score(bonus_entry, attendance_entry)

        assignments: list[tuple[int, int, float]] = []

        if linear_sum_assignment is not None and matrix.size:
            cost_matrix = 1.0 - matrix
            row_indices, col_indices = linear_sum_assignment(cost_matrix)
            for row, col in zip(row_indices, col_indices):
                score = float(matrix[row, col])
                if score >= self.MATCH_THRESHOLD:
                    assignments.append((int(row), int(col), score))
        else:
            candidate_pairs: list[tuple[int, int, float]] = []
            for row in range(matrix.shape[0]):
                for col in range(matrix.shape[1]):
                    score = float(matrix[row, col])
                    if score >= self.MATCH_THRESHOLD:
                        candidate_pairs.append((row, col, score))

            candidate_pairs.sort(key=lambda item: item[2], reverse=True)
            used_rows: set[int] = set()
            used_cols: set[int] = set()
            for row, col, score in candidate_pairs:
                if row in used_rows or col in used_cols:
                    continue
                assignments.append((int(row), int(col), score))
                used_rows.add(int(row))
                used_cols.add(int(col))

        if not assignments:
            self._set_status("No confident matches found. Adjust totals manually if needed.", tone="warning")
            return

        updates_applied = 0
        matched_rows = set()

        for row, col, score in assignments:
            bonus_entry = self._bonus_summary[row]
            record = self._attendance_records[col]
            record_id = int(record.get("id"))

            bonus_value = int(bonus_entry.get("total_bonus", 0) or 0)
            a_value = int(record.get("a_point", 0) or 0)
            new_total = a_value + bonus_value
            current_total = int(record.get("t_point", 0) or 0)
            current_bonus = int(record.get("b_point", 0) or 0)

            if new_total == current_total and bonus_value == current_bonus:
                matched_rows.add(row)
                continue

            record["b_point"] = bonus_value
            record["t_point"] = new_total

            self._invalid_entries.discard(record_id)
            self._mark_entry_invalid(record_id, False, target="both")

            self._suspend_entry_updates.add(record_id)
            try:
                total_var = self._attendance_value_vars.get(record_id)
                if total_var is not None:
                    total_var.set(str(new_total))
                bonus_var = self._attendance_bonus_vars.get(record_id)
                if bonus_var is not None:
                    bonus_var.set(str(bonus_value))
            finally:
                self._suspend_entry_updates.discard(record_id)

            updates_applied += 1
            matched_rows.add(row)

        unmatched_rows = [index for index in range(bonus_count) if index not in matched_rows]

        if updates_applied:
            self._set_unsaved_changes(True)
            message = f"Auto-match applied to {updates_applied} record(s)."
            if unmatched_rows:
                names = [self._bonus_summary[idx].get("student_name") or "Unnamed" for idx in unmatched_rows]
                preview = ", ".join(names[:3])
                if len(names) > 3:
                    preview += "…"
                message += f" Unmatched bonus: {preview}."
            self._set_status(message + " Save to persist changes.", tone="success")
        else:
            message = "Auto-match found existing alignments; no changes were necessary."
            if unmatched_rows:
                names = [self._bonus_summary[idx].get("student_name") or "Unnamed" for idx in unmatched_rows]
                preview = ", ".join(names[:3])
                if len(names) > 3:
                    preview += "…"
                message += f" Remaining unmatched: {preview}."
            self._set_status(message, tone="info")

        self._update_summary()
        self._update_export_requirements()

    def _normalize_name(self, value: str | None) -> str:
        if not value:
            return ""
        return "".join(ch.lower() for ch in value if ch.isalnum())

    def _tokenize_name(self, value: str | None) -> list[str]:
        if not value:
            return []
        sanitized = value.replace("-", " ")
        return [token.strip().lower() for token in sanitized.split() if token.strip()]

    def _compute_match_score(self, bonus_entry: dict[str, Any], record: dict[str, Any]) -> float:
        bonus_name_raw = bonus_entry.get("student_name")
        attendance_name_raw = record.get("student_name") or record.get("student_id")

        bonus_normalized = self._normalize_name(bonus_name_raw)
        attendance_normalized = self._normalize_name(attendance_name_raw)

        if not bonus_normalized or not attendance_normalized:
            return 0.0

        ratio = SequenceMatcher(None, bonus_normalized, attendance_normalized).ratio()

        bonus_tokens = set(self._tokenize_name(bonus_name_raw))
        attendance_tokens = set(self._tokenize_name(attendance_name_raw))

        if bonus_tokens and attendance_tokens:
            overlap = len(bonus_tokens & attendance_tokens)
            token_score = overlap / max(len(bonus_tokens), len(attendance_tokens))
            ratio = max(ratio, token_score)

        student_id = (record.get("student_id") or "").lower()
        bonus_lower = (bonus_entry.get("student_name") or "").lower()
        if student_id and student_id in bonus_lower:
            ratio = min(1.0, ratio + 0.25)

        return float(ratio)

    def _save_totals(self) -> None:
        if not self._selected_session:
            self._set_status("Select a session before saving.", tone="warning")
            return

        if self._invalid_entries:
            self._set_status("Resolve invalid totals before saving.", tone="warning")
            return

        session_id = self._selected_session["id"]
        updates: list[dict[str, Any]] = []

        for record in self._attendance_records:
            record_id = int(record.get("id"))
            total_value = int(record.get("t_point", 0) or 0)
            bonus_value = int(record.get("b_point", 0) or 0)
            a_value = int(record.get("a_point", 0) or 0)
            original_total = self._initial_totals.get(record_id, a_value + self._initial_bonuses.get(record_id, 0))
            original_bonus = self._initial_bonuses.get(record_id, 0)

            if total_value == original_total and bonus_value == original_bonus:
                continue

            payload: dict[str, Any] = {
                "id": record_id,
                "t_point": total_value,
                "b_point": bonus_value,
                "a_point": a_value,
            }

            if record.get("student_name") is not None:
                payload["student_name"] = record.get("student_name")

            updates.append(payload)
        update_count = len(updates)

        if updates:
            try:
                self._service.update_attendance_records(
                    session_id=session_id,
                    updates=updates,
                )
            except Exception as exc:  # pragma: no cover - database safeguard
                self._set_status(f"Failed to save totals: {exc}", tone="warning")
                return

        try:
            session_confirmed = self._service.confirm_attendance_for_session(session_id=session_id)
        except Exception as exc:  # pragma: no cover - database safeguard
            self._set_status(f"Failed to confirm attendance: {exc}", tone="warning")
            return

        for record in self._attendance_records:
            record_id = int(record.get("id"))
            record["status"] = "confirmed"
            self._initial_totals[record_id] = int(record.get("t_point", 0) or 0)
            self._initial_bonuses[record_id] = int(record.get("b_point", 0) or 0)

        if self._selected_session is not None:
            self._selected_session["attendance_confirmed_count"] = len(self._attendance_records)
            self._selected_session["attendance_count"] = len(self._attendance_records)
            if session_confirmed:
                self._selected_session["status"] = "confirmed"

        confirmation_message = (
            f"Saved totals for {update_count} record(s); attendance confirmed."
            if update_count
            else "Attendance confirmed for all records."
        )

        self._set_unsaved_changes(False)
        self._update_export_requirements()
        self._update_summary()
        self._set_status(confirmation_message, tone="success")

    def _update_summary(self) -> None:
        total_attendance = len(self._attendance_records)
        confirmed_attendance = sum(1 for record in self._attendance_records if record.get("status") == "confirmed")
        bonus_rows = sum(int(entry.get("record_count", 0) or 0) for entry in self._bonus_summary)

        if total_attendance == 0 and bonus_rows == 0:
            self._summary_var.set("")
            return

        summary_parts = []
        if total_attendance:
            summary_parts.append(
                f"Students listed: {total_attendance}"
            )
            summary_parts.append(f"Confirmed: {confirmed_attendance}")
        if bonus_rows:
            summary_parts.append(f"Bonus records: {bonus_rows}")
        self._summary_var.set(" · ".join(summary_parts))

    # ------------------------------------------------------------------
    # Export helpers
    # ------------------------------------------------------------------
    def _prepare_export_dataset(self) -> tuple[list[str], list[list[Any]]]:
        headers = [
            "Student ID",
            "Student name",
            "Attendance point",
            "Bonus point",
            "Total point",
            "Recorded at",
        ]

        rows: list[list[Any]] = []
        for record in self._attendance_records:
            rows.append(
                [
                    record.get("student_id"),
                    record.get("student_name"),
                    record.get("a_point"),
                    record.get("b_point"),
                    record.get("t_point"),
                    record.get("recorded_at"),
                ]
            )

        return headers, rows

    def _build_export_filename_stub(self) -> str:
        session = self._selected_session or {}

        chapter_raw = (session.get("chapter_code") or "").strip()
        if chapter_raw:
            chapter_token = chapter_raw.upper()
            if not chapter_token.startswith("C"):
                chapter_token = f"C{chapter_token}"
        else:
            chapter_token = "C-"

        weekday_label = WEEKDAY_LABELS.get(session.get("weekday_index"), "Weekday")

        start_hour = session.get("start_hour")
        end_hour = session.get("end_hour")
        start_text = f"{int(start_hour):02d}:00" if start_hour is not None else "00:00"
        end_text = f"{int(end_hour):02d}:00" if end_hour is not None else "00:00"

        raw_name = f"{chapter_token} {weekday_label} {start_text}-{end_text}"

        sanitized = raw_name.replace("·", "-").replace("\x7f", "")
        sanitized = sanitized.replace(":", ".")
        sanitized = re.sub(r'[<>:"/\\|?*]', "_", sanitized)
        sanitized = re.sub(r"\s+", " ", sanitized).strip()
        sanitized = sanitized.strip("._ ")

        return sanitized or "attendance_export"

    def _export_csv(self) -> None:
        if not self._selected_session:
            self._set_status("Select a session before exporting.", tone="warning")
            return

        file_name = filedialog.asksaveasfilename(
            title="Export attendance to CSV",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile=f"{self._build_export_filename_stub()}.csv",
        )
        if not file_name:
            return

        headers, rows = self._prepare_export_dataset()

        try:
            with open(file_name, "w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(headers)
                writer.writerows(rows)
        except OSError as exc:
            self._set_status(f"Failed to export CSV: {exc}", tone="warning")
            return

        self._set_status(f"Exported {len(self._attendance_records)} rows to CSV.", tone="success")

    def _export_excel(self) -> None:
        if not self._selected_session:
            self._set_status("Select a session before exporting.", tone="warning")
            return
        if Workbook is None:
            self._set_status("openpyxl is required for Excel export.", tone="warning")
            return

        file_name = filedialog.asksaveasfilename(
            title="Export attendance to Excel",
            defaultextension=".xlsx",
            filetypes=[("Excel Workbook", "*.xlsx"), ("All files", "*.*")],
            initialfile=f"{self._build_export_filename_stub()}.xlsx",
        )
        if not file_name:
            return

        wb = Workbook()
        sheet = wb.active
        sheet.title = "Attendance"

        headers, rows = self._prepare_export_dataset()
        sheet.append(headers)
        for row in rows:
            sheet.append(row)

        try:
            Path(file_name).parent.mkdir(parents=True, exist_ok=True)
            wb.save(file_name)
        except OSError as exc:
            self._set_status(f"Failed to export Excel: {exc}", tone="warning")
            return

        self._set_status(f"Exported {len(self._attendance_records)} rows to Excel.", tone="success")

    def _describe_session(self, session: dict[str, Any]) -> str:
        weekday_label = WEEKDAY_LABELS.get(session.get("weekday_index"), f"Day {session.get('weekday_index')}")
        return (
            f"{session.get('chapter_code')} · {weekday_label}"
            f" {session.get('start_hour'):02d}:00-{session.get('end_hour'):02d}:00"
        )

    def _format_session_text(self, session: dict[str, Any]) -> str:
        weekday_label = WEEKDAY_LABELS.get(session.get("weekday_index"), f"Day {session.get('weekday_index')}")
        attendance_line = (
            f"Attendance {session.get('attendance_confirmed_count', 0)}/{session.get('attendance_count', 0)}"
        )
        bonus_line = f"Bonus {session.get('bonus_confirmed_count', 0)}/{session.get('bonus_count', 0)}"
        return (
            f"{session.get('chapter_code')} · {weekday_label}\n"
            f"{attendance_line} · {bonus_line}"
        )

    def _format_hour_range(self, start: int, end: int) -> str:
        return f"{start:02d}:00-{end:02d}:00"

    def _parse_hour_range(self, label: str) -> tuple[int | None, int | None]:
        try:
            start_text, end_text = label.split("-")
            return int(start_text.split(":")[0]), int(end_text.split(":")[0])
        except ValueError:
            return None, None

    def _set_status(self, message: str, tone: str = "info") -> None:
        self._status_var.set(message)
        color_map = {
            "info": VS_TEXT_MUTED,
            "warning": VS_WARNING,
            "success": VS_SUCCESS,
        }
        self._status_label.configure(text_color=color_map.get(tone, VS_TEXT_MUTED))

    def _toggle_action_buttons(self, *, enabled: bool) -> None:
        self._detail_ready = enabled

        refresh_state = "normal" if enabled else "disabled"
        self._refresh_button.configure(state=refresh_state)

        match_state = "normal" if enabled and self._bonus_summary else "disabled"
        self._match_button.configure(state=match_state)

        self._update_save_button_state()
        self._update_export_state()

    def _update_save_button_state(self) -> None:
        if not hasattr(self, "_save_button"):
            return

        if not self._detail_ready:
            state = "disabled"
        elif self._invalid_entries:
            state = "disabled"
        elif self._unsaved_changes:
            state = "normal"
        else:
            state = "disabled"

        self._save_button.configure(state=state)

    def _update_export_state(self) -> None:
        if not hasattr(self, "_export_csv_button"):
            return

        if (
            not self._detail_ready
            or self._unsaved_changes
            or self._requires_bonus_alignment
            or self._invalid_entries
        ):
            csv_state = "disabled"
        else:
            csv_state = "normal"

        self._export_csv_button.configure(state=csv_state)

        excel_state = csv_state if Workbook is not None else "disabled"
        self._export_excel_button.configure(state=excel_state)

    def _set_unsaved_changes(self, value: bool) -> None:
        if self._unsaved_changes == value:
            self._update_save_button_state()
            self._update_export_state()
            return

        self._unsaved_changes = value
        self._update_save_button_state()
        self._update_export_state()

    def _update_export_requirements(self) -> None:
        self._requires_bonus_alignment = self._has_bonus_gap()
        self._update_export_state()

    def _has_bonus_gap(self) -> bool:
        if not self._bonus_summary:
            return False

        expected_bonus = sum(int(entry.get("total_bonus", 0) or 0) for entry in self._bonus_summary)
        applied_bonus = sum(int(record.get("b_point", 0) or 0) for record in self._attendance_records)

        return applied_bonus != expected_bonus
