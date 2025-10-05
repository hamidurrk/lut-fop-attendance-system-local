from __future__ import annotations

import threading
from typing import Any, Callable

import customtkinter as ctk

from attendance_app.automation import (
    AutoGradingResult,
    AutoGradingSessionContext,
    ChromeAutomationError,
    ChromeRemoteController,
)
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

AutoGradingHandler = Callable[[ChromeRemoteController, str, str, int, bool, AutoGradingSessionContext], AutoGradingResult | bool]


class AutoGraderView(ctk.CTkFrame):
    """Browse confirmed sessions and run automated grading."""

    def __init__(
        self,
        master: Any,
        attendance_service: AttendanceService,
        *,
        chrome_controller: ChromeRemoteController | None = None,
        on_detail_open: Callable[[], None] | None = None,
        on_detail_close: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(master, fg_color=VS_BG)
        self._service = attendance_service
        self._chrome_controller = chrome_controller
        self._on_detail_open = on_detail_open
        self._on_detail_close = on_detail_close

        self._sessions: list[dict[str, Any]] = []
        self._session_rows: list[dict[str, Any]] = []
        self._selected_session: dict[str, Any] | None = None

        self._attendance_records: list[dict[str, Any]] = []
        self._record_rows: dict[int, dict[str, Any]] = {}

        self._summary_var = ctk.StringVar(value="")
        self._status_var = ctk.StringVar(value="Select a session to begin auto-grading.")
        self._status_color = VS_TEXT_MUTED

        self._auto_save_var = ctk.BooleanVar(value=True)
        self._automation_running = False
        self._stop_requested = False
        self._automation_thread: threading.Thread | None = None
        self._grading_handler: AutoGradingHandler | None = None
        self._current_processing_id: int | None = None

        self._session_list: ctk.CTkScrollableFrame | None = None
        self._empty_sessions_label: ctk.CTkLabel | None = None
        self._records_table: ctk.CTkScrollableFrame | None = None
        self._records_header_row: ctk.CTkFrame | None = None
        self._session_title: ctk.CTkLabel | None = None
        self._status_label: ctk.CTkLabel | None = None
        self._summary_label: ctk.CTkLabel | None = None
        self._start_button: ctk.CTkButton | None = None
        self._open_chrome_button: ctk.CTkButton | None = None
        self._emergency_button: ctk.CTkButton | None = None
        self._automation_status_label: ctk.CTkLabel | None = None
        self._prompt_frame: ctk.CTkFrame | None = None
        self._prompt_label: ctk.CTkLabel | None = None
        self._prompt_yes_button: ctk.CTkButton | None = None
        self._prompt_no_button: ctk.CTkButton | None = None
        self._back_button: ctk.CTkButton | None = None

        self._container: ctk.CTkFrame | None = None
        self._list_page: ctk.CTkFrame | None = None
        self._detail_page: ctk.CTkFrame | None = None
        self._showing_detail = False

        self._session_context: AutoGradingSessionContext | None = None
        self._prompt_event: threading.Event | None = None
        self._prompt_response_holder: dict[str, bool] | None = None

        self._build_layout()
        self._load_sessions()
        self._update_controls_state()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    def _build_layout(self) -> None:
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        container = ctk.CTkFrame(self, fg_color=VS_SURFACE, corner_radius=16)
        container.grid(row=0, column=0, sticky="nsew", padx=24, pady=24)
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)
        self._container = container

        list_page = ctk.CTkFrame(container, fg_color="transparent")
        list_page.grid(row=0, column=0, sticky="nsew")
        list_page.grid_rowconfigure(0, weight=1)
        list_page.grid_columnconfigure(0, weight=1)
        self._list_page = list_page

        self._build_session_panel(list_page)

        detail_page = ctk.CTkFrame(container, fg_color="transparent")
        detail_page.grid(row=0, column=0, sticky="nsew")
        detail_page.grid_rowconfigure(0, weight=1)
        detail_page.grid_columnconfigure(0, weight=1)
        detail_page.grid_remove()
        self._detail_page = detail_page

        self._build_detail_page(detail_page)

    def _show_sessions_page(self, *, reset_status: bool = False) -> None:
        was_detail = self._showing_detail
        if self._list_page is not None:
            self._list_page.grid()
        if self._detail_page is not None:
            self._detail_page.grid_remove()
        self._showing_detail = False
        if was_detail and self._on_detail_close is not None:
            self._on_detail_close()
        if reset_status:
            self._summary_var.set("")
            if not self._automation_running:
                self._set_status("Select a session to begin auto-grading.")
        self._update_controls_state()

    def _show_detail_page(self) -> None:
        if self._list_page is not None:
            self._list_page.grid_remove()
        if self._detail_page is not None:
            self._detail_page.grid()
        if not self._showing_detail and self._on_detail_open is not None:
            self._on_detail_open()
        self._showing_detail = True
        self._update_controls_state()

    def _handle_back_to_sessions(self) -> None:
        if self._automation_running:
            return
        self._selected_session = None
        self._highlight_selected_session()
        self._attendance_records = []
        self._render_attendance_rows()
        self._update_summary()
        self._show_sessions_page(reset_status=True)

    def _build_session_panel(self, parent: ctk.CTkFrame) -> None:
        panel = ctk.CTkFrame(parent, fg_color=VS_SURFACE_ALT, corner_radius=18)
        panel.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
        panel.grid_rowconfigure(2, weight=1)
        panel.grid_columnconfigure(0, weight=1)

        header = ctk.CTkLabel(
            panel,
            text="Sessions",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=VS_TEXT,
        )
        header.grid(row=0, column=0, sticky="w", padx=24, pady=(20, 8))

        header_row = ctk.CTkFrame(panel, fg_color=VS_SURFACE, corner_radius=12)
        header_row.grid(row=1, column=0, sticky="ew", padx=24, pady=(0, 8))
        column_weights = (2, 1, 2, 1, 1)
        for index, weight in enumerate(column_weights):
            header_row.grid_columnconfigure(index, weight=weight, uniform="auto_session_cols")

        columns = [
            ("Chapter", 0, "w"),
            ("Week", 1, "center"),
            ("Day & time", 2, "w"),
            ("Attendance", 3, "center"),
            ("Graded", 4, "center"),
        ]
        for text, column, anchor in columns:
            justification = "left" if anchor == "w" else "center"
            ctk.CTkLabel(
                header_row,
                text=text,
                font=ctk.CTkFont(size=16, weight="bold"),
                text_color=VS_TEXT,
                anchor=anchor,
                justify=justification,
            ).grid(row=0, column=column, sticky="ew", padx=(16 if column == 0 else 12, 16))

        self._session_list = ctk.CTkScrollableFrame(
            panel,
            fg_color=VS_SURFACE,
            corner_radius=12,
            scrollbar_fg_color=VS_BORDER,
            scrollbar_button_color=VS_ACCENT,
        )
        self._session_list.grid(row=2, column=0, sticky="nsew", padx=18, pady=(0, 20))
        self._session_list.grid_columnconfigure(0, weight=1)

        self._empty_sessions_label = ctk.CTkLabel(
            self._session_list,
            text="No confirmed sessions are available for grading.",
            text_color=VS_TEXT_MUTED,
            font=ctk.CTkFont(size=15),
        )
        self._empty_sessions_label.grid(row=0, column=0, padx=16, pady=16)

    def _build_detail_page(self, parent: ctk.CTkFrame) -> None:
        wrapper = ctk.CTkFrame(parent, fg_color=VS_SURFACE_ALT, corner_radius=18)
        wrapper.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
        wrapper.grid_rowconfigure(0, weight=1)
        wrapper.grid_columnconfigure(0, weight=3)
        wrapper.grid_columnconfigure(1, weight=2)

        detail_column = ctk.CTkFrame(wrapper, fg_color="transparent")
        detail_column.grid(row=0, column=0, sticky="nsew", padx=(24, 12), pady=24)
        detail_column.grid_rowconfigure(3, weight=1)
        detail_column.grid_columnconfigure(0, weight=1)

        automation_column = ctk.CTkFrame(wrapper, fg_color="transparent")
        automation_column.grid(row=0, column=1, sticky="nsew", padx=(12, 24), pady=24)
        automation_column.grid_rowconfigure(0, weight=1)
        automation_column.grid_columnconfigure(0, weight=1)

        self._build_detail_column(detail_column)
        self._build_automation_panel(automation_column)

    def _build_detail_column(self, parent: ctk.CTkFrame) -> None:
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(3, weight=1)

        top_bar = ctk.CTkFrame(parent, fg_color="transparent")
        top_bar.grid(row=0, column=0, sticky="ew")
        top_bar.grid_columnconfigure(0, weight=0)
        top_bar.grid_columnconfigure(1, weight=1)
        top_bar.grid_columnconfigure(2, weight=0)

        self._back_button = ctk.CTkButton(
            top_bar,
            text="◀ Sessions",
            command=self._handle_back_to_sessions,
            fg_color=VS_SURFACE,
            hover_color=VS_ACCENT,
            text_color=VS_TEXT,
            border_width=1,
            border_color=VS_DIVIDER,
            height=40,
            width=130,
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self._back_button.grid(row=0, column=0, sticky="w", padx=(0, 16), pady=(0, 12))

        self._session_title = ctk.CTkLabel(
            top_bar,
            text="Auto-grader",
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color=VS_TEXT,
            anchor="w",
        )
        self._session_title.grid(row=0, column=1, sticky="w", pady=(0, 12))

        self._emergency_button = ctk.CTkButton(
            top_bar,
            text="Emergency stop",
            command=self._handle_emergency_stop,
            fg_color="#f26d6d",
            hover_color="#d95a5a",
            text_color=VS_TEXT,
            height=44,
            width=160,
            font=ctk.CTkFont(size=15, weight="bold"),
        )
        self._emergency_button.grid(row=0, column=2, sticky="e", pady=(0, 12))

        info_bar = ctk.CTkFrame(parent, fg_color="transparent")
        info_bar.grid(row=1, column=0, sticky="ew", pady=(0, 6))
        info_bar.grid_columnconfigure(0, weight=1)

        self._summary_label = ctk.CTkLabel(
            info_bar,
            textvariable=self._summary_var,
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=VS_TEXT,
            anchor="w",
        )
        self._summary_label.grid(row=0, column=0, sticky="w")

        self._status_label = ctk.CTkLabel(
            info_bar,
            textvariable=self._status_var,
            font=ctk.CTkFont(size=14),
            text_color=VS_TEXT_MUTED,
            anchor="w",
            wraplength=440,
            justify="left",
        )
        self._status_label.grid(row=1, column=0, sticky="w", pady=(4, 0))

        self._build_attendance_header(parent)
        self._build_attendance_table(parent)

    def _build_attendance_header(self, parent: ctk.CTkFrame) -> None:
        self._records_header_row = ctk.CTkFrame(parent, fg_color=VS_SURFACE, corner_radius=12)
        self._records_header_row.grid(row=2, column=0, sticky="ew", padx=24, pady=(0, 6))
        columns = [
            ("Student", 0, 2),
            ("Student ID", 1, 1),
            ("Total points", 2, 1),
            ("Status", 3, 1),
        ]
        for text, column, weight in columns:
            self._records_header_row.grid_columnconfigure(column, weight=weight, uniform="auto_records_cols")
            ctk.CTkLabel(
                self._records_header_row,
                text=text,
                font=ctk.CTkFont(size=16, weight="bold"),
                text_color=VS_TEXT,
                anchor="w" if column == 0 else "center",
            ).grid(
                row=0,
                column=column,
                sticky="ew",
                padx=(16 if column == 0 else 12, 16 if column == len(columns) - 1 else 12),
                pady=10,
            )

    def _build_attendance_table(self, parent: ctk.CTkFrame) -> None:
        self._records_table = ctk.CTkScrollableFrame(
            parent,
            fg_color=VS_SURFACE,
            corner_radius=12,
            scrollbar_fg_color=VS_BORDER,
            scrollbar_button_color=VS_ACCENT,
        )
        self._records_table.grid(row=3, column=0, sticky="nsew", padx=24, pady=(0, 16))
        self._records_table.grid_columnconfigure(0, weight=1)

    def _build_automation_panel(self, parent: ctk.CTkFrame) -> None:
        parent.grid_rowconfigure(0, weight=1)

        panel = ctk.CTkFrame(parent, fg_color=VS_SURFACE, corner_radius=16, border_width=1, border_color=VS_DIVIDER)
        panel.grid(row=0, column=0, sticky="nsew")
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_columnconfigure(1, weight=1)
        panel.grid_columnconfigure(2, weight=1)
        panel.grid_columnconfigure(3, weight=0)

        title = ctk.CTkLabel(
            panel,
            text="Automation",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=VS_TEXT,
            anchor="w",
        )
        title.grid(row=0, column=0, columnspan=4, sticky="w", padx=20, pady=(18, 8))

        description = ctk.CTkLabel(
            panel,
            text=(
                "Launch Chrome and start the auto-grader. Each student will run through the registered"
                " Selenium workflow sequentially."
            ),
            font=ctk.CTkFont(size=13),
            text_color=VS_TEXT_MUTED,
            wraplength=360,
            justify="left",
        )
        description.grid(row=1, column=0, columnspan=4, sticky="w", padx=20, pady=(0, 16))

        self._open_chrome_button = ctk.CTkButton(
            panel,
            text="Open Google Chrome",
            command=self._handle_open_chrome,
            fg_color=VS_SURFACE_ALT,
            hover_color=VS_ACCENT,
            border_width=1,
            border_color=VS_DIVIDER,
            text_color=VS_TEXT,
            height=46,
            font=ctk.CTkFont(size=15, weight="bold"),
        )
        self._open_chrome_button.grid(row=2, column=0, columnspan=2, padx=20, pady=(0, 18), sticky="ew")

        self._start_button = ctk.CTkButton(
            panel,
            text="Start auto-grading",
            command=self._start_auto_grading,
            fg_color=VS_ACCENT,
            hover_color=VS_ACCENT_HOVER,
            text_color=VS_TEXT,
            height=46,
            font=ctk.CTkFont(size=15, weight="bold"),
        )
        self._start_button.grid(row=2, column=2, columnspan=2, padx=(0, 20), pady=(0, 18), sticky="ew")

        auto_save_row = ctk.CTkFrame(panel, fg_color="transparent")
        auto_save_row.grid(row=3, column=0, columnspan=4, sticky="w", padx=20, pady=(0, 20))
        auto_save_row.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            auto_save_row,
            text="Auto-save after grading",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=VS_TEXT,
        ).grid(row=0, column=0, sticky="w")

        auto_save_switch = ctk.CTkSwitch(
            auto_save_row,
            variable=self._auto_save_var,
            text="",
            onvalue=True,
            offvalue=False,
        )
        auto_save_switch.grid(row=0, column=1, sticky="w", padx=(12, 0))

        status_title = ctk.CTkLabel(
            panel,
            text="Status",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=VS_TEXT,
            anchor="w",
        )
        status_title.grid(row=4, column=0, columnspan=4, sticky="w", padx=20, pady=(0, 6))

        self._automation_status_label = ctk.CTkLabel(
            panel,
            textvariable=self._status_var,
            font=ctk.CTkFont(size=13),
            text_color=self._status_color,
            anchor="w",
            justify="left",
            wraplength=360,
        )
        self._automation_status_label.grid(row=5, column=0, columnspan=4, sticky="ew", padx=20, pady=(0, 20))

        prompt_frame = ctk.CTkFrame(panel, fg_color=VS_SURFACE_ALT, corner_radius=12)
        prompt_frame.grid(row=6, column=0, columnspan=4, sticky="ew", padx=20, pady=(0, 20))
        prompt_frame.grid_columnconfigure(0, weight=1)
        prompt_frame.grid_remove()
        self._prompt_frame = prompt_frame

        self._prompt_label = ctk.CTkLabel(
            prompt_frame,
            text="",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=VS_TEXT,
            justify="left",
            anchor="w",
            wraplength=320,
        )
        self._prompt_label.grid(row=0, column=0, columnspan=2, sticky="ew", padx=16, pady=(14, 10))

        buttons_row = ctk.CTkFrame(prompt_frame, fg_color="transparent")
        buttons_row.grid(row=1, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 14))
        buttons_row.grid_columnconfigure(0, weight=1)
        buttons_row.grid_columnconfigure(1, weight=1)

        self._prompt_yes_button = ctk.CTkButton(
            buttons_row,
            text="Yes",
            fg_color=VS_ACCENT,
            hover_color=VS_ACCENT_HOVER,
            text_color=VS_TEXT,
            command=lambda: self._resolve_prompt(True),
        )
        self._prompt_yes_button.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        self._prompt_no_button = ctk.CTkButton(
            buttons_row,
            text="No",
            fg_color=VS_SURFACE,
            hover_color=VS_ACCENT,
            text_color=VS_TEXT,
            border_width=1,
            border_color=VS_DIVIDER,
            command=lambda: self._resolve_prompt(False),
        )
        self._prompt_no_button.grid(row=0, column=1, sticky="ew", padx=(8, 0))

    # ------------------------------------------------------------------
    # Session handling
    # ------------------------------------------------------------------
    def _load_sessions(self) -> None:
        sessions = self._service.list_sessions()
        confirmed_sessions = [session for session in sessions if (session.get("status") or "").lower() == "confirmed"]
        self._render_session_rows(confirmed_sessions)

    def _render_session_rows(self, sessions: list[dict[str, Any]]) -> None:
        if self._session_list is None or self._empty_sessions_label is None:
            return

        selected_id = self._selected_session.get("id") if self._selected_session else None

        for row in self._session_rows:
            row["frame"].destroy()
        self._session_rows.clear()
        self._sessions = sessions

        self._selected_session = None
        if selected_id is not None:
            for session in sessions:
                if session.get("id") == selected_id:
                    self._selected_session = session
                    break

        if not sessions:
            self._empty_sessions_label.grid()
            self._selected_session = None
            self._attendance_records = []
            self._render_attendance_rows()
            self._update_summary()
            self._update_controls_state()
            if not self._automation_running:
                self._set_status("No confirmed sessions available for auto-grading.", tone="warning")
            self._show_sessions_page(reset_status=False)
            return

        self._empty_sessions_label.grid_remove()

        day_lookup = WEEKDAY_LABELS

        column_weights = (2, 1, 2, 1, 1)

        for index, session in enumerate(sessions):
            row_frame = ctk.CTkFrame(
                self._session_list,
                fg_color=VS_SURFACE_ALT,
                corner_radius=12,
                border_width=1,
                border_color=VS_DIVIDER,
            )
            row_frame.grid(row=index, column=0, sticky="ew", padx=16, pady=6)
            for col_index, weight in enumerate(column_weights):
                row_frame.grid_columnconfigure(col_index, weight=weight, uniform="auto_session_cols")

            chapter = session.get("chapter_code") or "—"
            week_number = session.get("week_number")
            week = f"W{week_number}" if week_number is not None else "—"
            weekday_label = day_lookup.get(session.get("weekday_index"), "Day ?")
            start_hour = session.get("start_hour")
            end_hour = session.get("end_hour")
            if start_hour is None or end_hour is None:
                time_range = "—"
            else:
                time_range = f"{int(start_hour):02d}:00-{int(end_hour):02d}:00"
            schedule = f"{weekday_label} · {time_range}"
            attendance_total = int(session.get("attendance_count", 0) or 0)
            graded_total = int(session.get("graded_count", 0) or 0)

            values = [
                (chapter, 0, "w", VS_TEXT),
                (week, 1, "center", VS_TEXT),
                (schedule, 2, "w", VS_TEXT),
                (str(attendance_total), 3, "center", VS_TEXT_MUTED),
                (f"{graded_total}/{attendance_total}" if attendance_total else "0/0", 4, "center", VS_TEXT_MUTED),
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
                    font=ctk.CTkFont(size=15),
                    text_color=color,
                    anchor=anchor,
                    justify=justification,
                )
                label.grid(
                    row=0,
                    column=column,
                    sticky="ew",
                    padx=(16 if column == 0 else 12, 16 if column == len(values) - 1 else 12),
                    pady=10,
                )
                label.bind("<Button-1>", lambda _event, payload=session: self._handle_session_select(payload))
                label.bind("<Enter>", lambda _event, info=row_info: self._on_session_row_enter(info))
                label.bind("<Leave>", lambda event, info=row_info: self._on_session_row_leave(info, event))
                row_info["labels"].append(label)
                row_info["default_colors"].append(color)

            row_frame.bind("<Button-1>", lambda _event, payload=session: self._handle_session_select(payload))
            row_frame.bind("<Enter>", lambda _event, info=row_info: self._on_session_row_enter(info))
            row_frame.bind("<Leave>", lambda event, info=row_info: self._on_session_row_leave(info, event))
            row_frame.configure(cursor="hand2")

            self._session_rows.append(row_info)

        self._highlight_selected_session()
        self._update_summary()
        self._update_controls_state()
        if self._showing_detail and self._selected_session is None:
            self._show_sessions_page(reset_status=True)

    def _handle_session_select(self, session: dict[str, Any]) -> None:
        if self._automation_running:
            return
        self._selected_session = session
        self._highlight_selected_session()
        self._show_detail_page()
        self._load_session_details(int(session["id"]))
        self._update_controls_state()

    def _highlight_selected_session(self) -> None:
        selected_id = self._selected_session["id"] if self._selected_session else None
        for row_info, session in zip(self._session_rows, self._sessions):
            is_selected = selected_id is not None and session.get("id") == selected_id
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
        if self._selected_session and session_id == self._selected_session.get("id"):
            return
        if row_info.get("hovered"):
            return
        self._set_session_row_state(row_info, selected=False, hovered=True)

    def _on_session_row_leave(self, row_info: dict[str, Any], event: Any) -> None:
        frame: ctk.CTkFrame = row_info["frame"]
        if not frame.winfo_exists():
            return

        widget = frame.winfo_containing(event.x_root, event.y_root)
        if widget is not None and self._widget_belongs_to_row(widget, frame):
            return

        session_id = row_info.get("session_id")
        is_selected = self._selected_session and session_id == self._selected_session.get("id")
        self._set_session_row_state(row_info, selected=bool(is_selected), hovered=False)

    def _widget_belongs_to_row(self, widget: Any, row_frame: ctk.CTkFrame) -> bool:
        current = widget
        while current is not None:
            if current == row_frame:
                return True
            current = getattr(current, "master", None)
        return False

    # ------------------------------------------------------------------
    # Session details
    # ------------------------------------------------------------------
    def _load_session_details(self, session_id: int) -> None:
        self._attendance_records = self._service.get_session_attendance(session_id)
        self._render_attendance_rows()
        self._update_summary()
        self._set_status("Ready to start auto-grading.")

    def _render_attendance_rows(self) -> None:
        if self._records_table is None:
            return

        for child in list(self._records_table.winfo_children()):
            child.destroy()
        self._record_rows.clear()

        if not self._attendance_records:
            placeholder = ctk.CTkLabel(
                self._records_table,
                text="No students recorded for this session.",
                text_color=VS_TEXT_MUTED,
                font=ctk.CTkFont(size=15),
            )
            placeholder.grid(row=0, column=0, padx=18, pady=18)
            return

        alternating_colors = (VS_SURFACE_ALT, VS_SURFACE)

        for index, record in enumerate(self._attendance_records):
            bg_color = alternating_colors[index % 2]
            record_id = int(record.get("id"))
            row_frame = ctk.CTkFrame(
                self._records_table,
                fg_color=bg_color,
                corner_radius=10,
                border_width=1,
                border_color=VS_DIVIDER,
            )
            row_frame.grid(row=index, column=0, sticky="ew", padx=12, pady=4)
            row_frame.grid_columnconfigure(0, weight=2)
            row_frame.grid_columnconfigure(1, weight=1)
            row_frame.grid_columnconfigure(2, weight=1)
            row_frame.grid_columnconfigure(3, weight=1)

            student_name = record.get("student_name") or record.get("student_id") or "Unknown"
            student_id = record.get("student_id") or "—"
            total_points = int(record.get("t_point", 0) or 0)
            status_raw = (record.get("status") or "recorded").replace("_", " ").title()

            labels: dict[str, ctk.CTkLabel] = {}

            labels["name"] = ctk.CTkLabel(
                row_frame,
                text=student_name,
                font=ctk.CTkFont(size=15),
                text_color=VS_TEXT,
                anchor="w",
            )
            labels["name"].grid(row=0, column=0, sticky="ew", padx=(16, 12), pady=10)

            labels["id"] = ctk.CTkLabel(
                row_frame,
                text=student_id,
                font=ctk.CTkFont(size=15),
                text_color=VS_TEXT_MUTED,
                anchor="center",
            )
            labels["id"].grid(row=0, column=1, sticky="ew", padx=12, pady=10)

            labels["points"] = ctk.CTkLabel(
                row_frame,
                text=str(total_points),
                font=ctk.CTkFont(size=15, weight="bold"),
                text_color=VS_TEXT,
                anchor="center",
            )
            labels["points"].grid(row=0, column=2, sticky="ew", padx=12, pady=10)

            labels["status"] = ctk.CTkLabel(
                row_frame,
                text=status_raw,
                font=ctk.CTkFont(size=15),
                text_color=VS_TEXT,
                anchor="center",
            )
            labels["status"].grid(row=0, column=3, sticky="ew", padx=(12, 16), pady=10)

            self._record_rows[record_id] = {
                "frame": row_frame,
                "labels": labels,
                "base_color": bg_color,
            }

    def _update_summary(self) -> None:
        session = self._selected_session or {}
        if not session:
            if self._session_title is not None:
                self._session_title.configure(text="Auto-grader")
            self._summary_var.set("")
            return

        weekday_label = WEEKDAY_LABELS.get(session.get("weekday_index"), f"Day {session.get('weekday_index')}")
        chapter = session.get("chapter_code", "?")
        week = session.get("week_number")
        start_hour = session.get("start_hour")
        end_hour = session.get("end_hour")
        time_range = "—"
        if start_hour is not None and end_hour is not None:
            time_range = f"{int(start_hour):02d}:00-{int(end_hour):02d}:00"

        if self._session_title is not None:
            self._session_title.configure(text=f"Session · {chapter} · W{week}")
        self._summary_var.set(f"{weekday_label} · {time_range} · {len(self._attendance_records)} students")

    # ------------------------------------------------------------------
    # Automation actions
    # ------------------------------------------------------------------
    def register_grading_handler(self, handler: AutoGradingHandler | None) -> None:
        """Register the Selenium workload that performs grading for a single student."""
        self._grading_handler = handler
        if handler is None:
            self._set_status("Automation handler not configured.", tone="warning")
        else:
            self._set_status("Automation handler ready. Select a session to begin.")
        self._update_controls_state()

    def _handle_open_chrome(self) -> None:
        if self._chrome_controller is None:
            self._set_status("Chrome automation is not configured.", tone="warning")
            return
        if self._automation_running:
            self._set_status("Auto-grading already running.", tone="warning")
            return

        if self._open_chrome_button is not None:
            self._open_chrome_button.configure(state="disabled")
        self._set_status("Opening Google Chrome…", tone="info")

        threading.Thread(target=self._open_chrome_async, daemon=True).start()

    def _open_chrome_async(self) -> None:
        controller = self._chrome_controller
        if controller is None:
            return

        try:
            controller.open_browser()
        except ChromeAutomationError as exc:
            message = f"Failed to open Chrome: {exc}"
            tone = "warning"
        except Exception as exc:  # pragma: no cover - guard unexpected issues
            message = f"Unexpected Chrome error: {exc}"
            tone = "warning"
        else:
            message = "Chrome is ready for auto-grading."
            tone = "success"

        self.after(0, lambda msg=message, tn=tone: self._finalize_open_chrome(msg, tn))

    def _finalize_open_chrome(self, message: str, tone: str) -> None:
        self._set_status(message, tone=tone)
        if self._open_chrome_button is not None and not self._automation_running:
            self._open_chrome_button.configure(state="normal")
        self._update_controls_state()

    def _start_auto_grading(self) -> None:
        if self._automation_running:
            return
        if self._selected_session is None:
            self._set_status("Select a session first.", tone="warning")
            return
        if not self._attendance_records:
            self._set_status("No students to grade in this session.", tone="warning")
            return
        if self._grading_handler is None:
            self._set_status("Register an automation handler before starting.", tone="warning")
            return

        self._automation_running = True
        self._stop_requested = False
        self._session_context = AutoGradingSessionContext(prompt_callback=self._prompt_user_confirmation)
        self._resolve_prompt(False)
        self._update_controls_state()
        self._set_status("Preparing auto-grading…")

        session_id = int(self._selected_session["id"])
        records_snapshot = [record.copy() for record in self._attendance_records]
        auto_save = self._auto_save_var.get()
        session_context = self._session_context or AutoGradingSessionContext(prompt_callback=self._prompt_user_confirmation)

        def worker() -> None:
            controller = self._chrome_controller
            if controller is not None:
                try:
                    controller.open_browser()
                except ChromeAutomationError as exc:
                    self.after(0, lambda msg=f"Chrome launch failed: {exc}": self._handle_automation_launch_failure(msg))
                    return
                except Exception as exc:  # pragma: no cover - guard unexpected issues
                    self.after(0, lambda msg=f"Unexpected Chrome error: {exc}": self._handle_automation_launch_failure(msg))
                    return

            self.after(0, lambda: self._set_status("Auto-grading in progress…"))

            for record in records_snapshot:
                if self._stop_requested:
                    break
                record_id = int(record.get("id"))
                status = (record.get("status") or "").lower()
                if status == "graded":
                    continue

                self._mark_record_processing(record_id, True)
                result = self._execute_grading_handler(record, auto_save, session_context)
                self._mark_record_processing(record_id, False)

                if self._stop_requested:
                    break

                if result:
                    try:
                        self._service.update_attendance_records(
                            session_id=session_id,
                            updates=[{"id": record_id, "status": "graded"}],
                        )
                    except Exception as exc:  # pragma: no cover - database layer should be reliable
                        self.after(0, lambda message=f"Failed to update record: {exc}": self._set_status(message, tone="warning"))
                        break

                    for stored in self._attendance_records:
                        if int(stored.get("id")) == record_id:
                            stored["status"] = "graded"
                            break

                    self._refresh_record_status(record_id, "graded")
                else:
                    self._refresh_record_status(record_id, record.get("status") or "recorded")

            stopped_flag = self._stop_requested
            self.after(0, lambda stopped=stopped_flag: self._on_automation_complete(stopped))

        self._automation_thread = threading.Thread(target=worker, daemon=True)
        self._automation_thread.start()

    def _execute_grading_handler(
        self,
        record: dict[str, Any],
        auto_save: bool,
        context: AutoGradingSessionContext,
    ) -> bool:
        handler = self._grading_handler
        if handler is None:
            return False
        controller = self._chrome_controller
        if controller is None:
            self.after(0, lambda: self._set_status("Chrome automation is not configured.", tone="warning"))
            return False
        student_name = record.get("student_name") or record.get("student_id") or ""
        student_id = record.get("student_id") or ""
        total_points = int(record.get("t_point", 0) or 0)
        context_obj = context or self._session_context or AutoGradingSessionContext(
            prompt_callback=self._prompt_user_confirmation
        )
        self._session_context = context_obj
        try:
            outcome = handler(controller, student_name, student_id, total_points, auto_save, context_obj)
        except Exception as exc:  # pragma: no cover - guard against handler crashes
            self.after(0, lambda message=f"Automation error for {student_id}: {exc}": self._set_status(message, tone="warning"))
            return False
        result = AutoGradingResult.ensure(outcome)
        if result.should_stop:
            self._stop_requested = True
        self.after(0, lambda res=result: self._handle_handler_feedback(res))
        return result.success

    def _handle_handler_feedback(self, result: AutoGradingResult) -> None:
        messages = [msg.text for msg in result.messages if msg.text and msg.text.strip()]
        if result.should_stop:
            messages.append("Auto-grader halted by automation routine.")
        if not messages:
            if result.success:
                messages.append("Auto-grading step completed.")
            else:
                messages.append("Auto-grading step reported no changes.")
        tone = result.dominant_tone() if result.messages else ("success" if result.success else "warning")
        if result.should_stop and tone != "warning":
            tone = "warning"
        self._set_status("\n".join(messages), tone=tone)

    def _mark_record_processing(self, record_id: int, processing: bool) -> None:
        self._current_processing_id = record_id if processing else None
        self.after(0, lambda: self._update_processing_state(record_id, processing))

    def _update_processing_state(self, record_id: int, processing: bool) -> None:
        row = self._record_rows.get(record_id)
        if not row:
            return
        frame: ctk.CTkFrame = row["frame"]
        base_color = row["base_color"]
        if processing:
            frame.configure(fg_color=VS_ACCENT, border_color=VS_ACCENT)
            for label in row["labels"].values():
                label.configure(text_color=VS_TEXT)
        else:
            frame.configure(fg_color=base_color, border_color=VS_DIVIDER)
            row["labels"]["name"].configure(text_color=VS_TEXT)
            row["labels"]["id"].configure(text_color=VS_TEXT_MUTED)
            row["labels"]["points"].configure(text_color=VS_TEXT)
            row["labels"]["status"].configure(text_color=VS_TEXT)

    def _refresh_record_status(self, record_id: int, status: str) -> None:
        display = status.replace("_", " ").title()
        self.after(0, lambda: self._apply_record_status(record_id, display))

    def _apply_record_status(self, record_id: int, display: str) -> None:
        row = self._record_rows.get(record_id)
        if not row:
            return
        row["labels"]["status"].configure(text=display)

    def _handle_automation_launch_failure(self, message: str) -> None:
        self._automation_running = False
        self._stop_requested = False
        self._session_context = None
        self._resolve_prompt(False)
        self._update_controls_state()
        self._set_status(message, tone="warning")

    def _on_automation_complete(self, stopped: bool) -> None:
        self._automation_running = False
        self._session_context = None
        self._resolve_prompt(False)
        self._update_controls_state()
        if stopped:
            self._set_status("Auto-grading cancelled.", tone="warning")
        else:
            self._set_status("Auto-grading finished.", tone="success")
        self._refresh_sessions()
        if self._selected_session is not None:
            self._load_session_details(int(self._selected_session["id"]))
        self._stop_requested = False
        self._automation_thread = None

    def _handle_emergency_stop(self) -> None:
        if not self._automation_running and self._chrome_controller is None:
            return
        self._stop_requested = True
        self._set_status("Emergency stop requested.", tone="warning")
        self._resolve_prompt(False)
        if self._chrome_controller is not None:
            try:
                self._chrome_controller.shutdown()
            except Exception:  # pragma: no cover - best effort
                pass
        self._update_controls_state()

    def _refresh_sessions(self) -> None:
        self._load_sessions()

    def refresh(self) -> None:
        """Public hook to refresh data when the view becomes visible."""
        if not self._automation_running:
            self._selected_session = None
        self._load_sessions()
        if self._automation_running and self._selected_session is not None:
            self._show_detail_page()
            self._load_session_details(int(self._selected_session["id"]))
        else:
            self._attendance_records = []
            self._render_attendance_rows()
            self._update_summary()
            self._show_sessions_page(reset_status=True)
        self._update_controls_state()

    # ------------------------------------------------------------------
    # Confirmation prompt helpers
    # ------------------------------------------------------------------
    def _prompt_user_confirmation(self, message: str) -> bool:
        active_event = self._prompt_event
        if active_event is not None and not active_event.is_set():
            raise RuntimeError("A confirmation prompt is already pending.")

        prompt_event = threading.Event()
        response_holder: dict[str, bool] = {}
        self._prompt_event = prompt_event
        self._prompt_response_holder = response_holder

        def show_prompt() -> None:
            self._show_prompt(message)

        self.after(0, show_prompt)
        prompt_event.wait()

        response = response_holder.get("response", False)
        self._prompt_event = None
        self._prompt_response_holder = None
        return bool(response)

    def _show_prompt(self, message: str) -> None:
        if self._prompt_label is not None:
            self._prompt_label.configure(text=message)
        if self._prompt_frame is not None:
            self._prompt_frame.grid()
        if self._prompt_yes_button is not None:
            self._prompt_yes_button.configure(state="normal")
        if self._prompt_no_button is not None:
            self._prompt_no_button.configure(state="normal")

    def _hide_prompt(self) -> None:
        if self._prompt_frame is not None:
            self._prompt_frame.grid_remove()
        if self._prompt_label is not None:
            self._prompt_label.configure(text="")

    def _resolve_prompt(self, value: bool) -> None:
        event = self._prompt_event
        holder = self._prompt_response_holder

        if holder is not None:
            holder["response"] = bool(value)

        self._hide_prompt()

        if event is not None and not event.is_set():
            event.set()

        self._prompt_event = None
        self._prompt_response_holder = None

    # ------------------------------------------------------------------
    # Status helpers
    # ------------------------------------------------------------------
    def _set_status(self, message: str, tone: str = "info") -> None:
        self._status_var.set(message)
        color_map = {
            "info": VS_TEXT_MUTED,
            "warning": VS_WARNING,
            "success": VS_SUCCESS,
        }
        new_color = color_map.get(tone, VS_TEXT_MUTED)
        self._status_color = new_color
        if self._status_label is not None:
            self._status_label.configure(text_color=new_color)
        if self._automation_status_label is not None:
            self._automation_status_label.configure(text_color=new_color)

    def _update_controls_state(self) -> None:
        session_selected = self._selected_session is not None
        can_start = session_selected and not self._automation_running and bool(self._grading_handler)
        if self._start_button is not None:
            self._start_button.configure(state="normal" if can_start else "disabled")
        if self._open_chrome_button is not None:
            self._open_chrome_button.configure(state="normal" if not self._automation_running else "disabled")
        if self._emergency_button is not None:
            self._emergency_button.configure(state="normal" if self._automation_running else "disabled")
        if self._back_button is not None:
            back_enabled = self._showing_detail and not self._automation_running
            self._back_button.configure(state="normal" if back_enabled else "disabled")