from __future__ import annotations

import tkinter.messagebox as messagebox
from tkinter import BooleanVar, IntVar, StringVar
from typing import Any, Callable, Mapping, Optional
import threading
import time
from pathlib import Path

import customtkinter as ctk
from PIL import Image, ImageOps

from attendance_app.automation import (
    ChromeAutomationError,
    ChromeRemoteController,
    get_bonus_student_data,
)
from attendance_app.automation.bonus_workflows import BonusAutomationResult
from attendance_app.models import AttendanceSession, BonusRecord, SessionTemplate, Student
from attendance_app.services import AttendanceService, DuplicateAttendanceError, DuplicateSessionError, QRScanner
from attendance_app.ui.theme import (
    VS_ACCENT,
    VS_ACCENT_HOVER,
    VS_BG,
    VS_BORDER,
    VS_CARD,
    VS_DIVIDER,
    VS_SURFACE,
    VS_SURFACE_ALT,
    VS_SUCCESS,
    VS_TEXT,
    VS_TEXT_MUTED,
    VS_WARNING,
)
from attendance_app.utils import InvalidHourRange, WEEKDAY_OPTIONS, format_relative_time, parse_hour_range
from attendance_app.config.settings import settings, user_settings_store

CAMPUS_OPTIONS: tuple[str, ...] = ("Lappeenranta", "Lahti")


class TakeAttendanceView(ctk.CTkFrame):
    WEEK_OPTIONS = tuple(str(week) for week in range(1, 15))

    def __init__(
        self,
        master,
        attendance_service: AttendanceService,
        *,
        chrome_controller: ChromeRemoteController | None = None,
        on_session_started: Callable[[], None] | None = None,
        on_session_ended: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(master, fg_color=VS_BG)
        self._service = attendance_service
        self._active_session_id: int | None = None
        self._chrome_controller = chrome_controller
        self._on_session_started = on_session_started
        self._on_session_ended = on_session_ended

        self._status_var = StringVar(value="Choose a session to get started.")
        self._session_info_var = StringVar(value="")
        self._qr_status_var = StringVar(value="Scanner idle")
        self._manual_status_var = StringVar(value="")
        self._bonus_status_var = StringVar(value="")
        self._bonus_info_var = StringVar(value="")
        self._bonus_output_var = StringVar(value="System messages will appear here.")
        self._bonus_default_output_message = self._bonus_output_var.get()
        self._bonus_student_details_var = StringVar(value="")
        self._bonus_instruction_launch = (
            "Launch the automated Chrome session to capture bonus records from CodeGrade."
        )
        self._bonus_instruction_ready = "Open student submission on CodeGrade to record bonus points."
        self._bonus_instruction_var = StringVar(value=self._bonus_instruction_launch)
        self._bonus_student_name_display = StringVar(value="")
        self._bonus_student_task_display = StringVar(value="")
        self._bonus_student_time_display = StringVar(value="")
        self._bonus_student_grade_display = StringVar(value="")
        self._bonus_student_file_display = StringVar(value="")

        self._chrome_icon_image: Image.Image | None = None
        self._chrome_icon: ctk.CTkImage | None = None
        self._chrome_inactive_message = "Chrome automation is not running. Launch Chrome to continue."
        self._chrome_ready_message = "Chrome automation ready."
        self._bonus_fetch_in_progress = False

        self._bonus_student_card: ctk.CTkFrame | None = None
        self._bonus_student_name_label: ctk.CTkLabel | None = None
        self._bonus_student_task_label: ctk.CTkLabel | None = None
        self._bonus_student_time_label: ctk.CTkLabel | None = None
        self._bonus_student_grade_label: ctk.CTkLabel | None = None
        self._bonus_student_file_chip: ctk.CTkLabel | None = None
        self._bonus_open_chrome_button: ctk.CTkButton | None = None
        self._chrome_state_poll_job: str | None = None
        self._chrome_state_probe_inflight = False

        self._chrome_icon_image, self._chrome_icon = self._load_icon_image("chrome.png", (18, 18))

        self.student_name_var = StringVar()
        self.student_id_var = StringVar()
        self._hide_student_id_var = BooleanVar(value=False)
        self.bonus_student_name_var = StringVar()
        self.bonus_point_var = StringVar()

        self.selected_template_label = StringVar(value="No session templates")
        self.selected_template_id = IntVar(value=0)
        self.chapter_var = StringVar()
        self.week_var = StringVar(value=self.WEEK_OPTIONS[0])

        self._templates: list[SessionTemplate] = []
        self._chrome_buttons: list[ctk.CTkButton] = []
        self._bonus_recent_list: ctk.CTkScrollableFrame | None = None
        self._bonus_status_label: ctk.CTkLabel | None = None
        self._bonus_automation_handlers: list[
            Callable[[ChromeRemoteController], BonusAutomationResult]
        ] = []
        self._bonus_get_student_button: ctk.CTkButton | None = None

        self._qr_scanner = QRScanner(camera_index=settings.qr_camera_index)
        self._qr_control_button: ctk.CTkButton | None = None
        self._qr_status_label: ctk.CTkLabel | None = None
        self._qr_preview_frame: ctk.CTkFrame | None = None
        self._qr_preview_label: ctk.CTkLabel | None = None
        self._qr_preview_image: ctk.CTkImage | None = None
        self._qr_preview_size: tuple[int, int] = (420, 420)
        placeholder_source = Image.new("RGB", self._qr_preview_size, color=(24, 24, 24))
        self._qr_preview_placeholder = ctk.CTkImage(
            light_image=placeholder_source,
            dark_image=placeholder_source.copy(),
            size=self._qr_preview_size,
        )
        self._qr_preview_busy = False
        self._qr_last_payload: Optional[str] = None
        self._qr_last_scan_time: float = 0.0
        self._qr_debounce_seconds: float = 1.2
        self._qr_default_border_color = VS_DIVIDER
        self._qr_scan_border_color = VS_SUCCESS
        self._qr_scan_border_duration_ms: int = 900
        self._qr_border_reset_job: str | None = None
        self._qr_auto_record_var = ctk.BooleanVar(value=bool(getattr(settings, "qr_auto_record", False)))
        self._qr_auto_record_switch: ctk.CTkSwitch | None = None
        self._qr_last_auto_record_payload: Optional[str] = None
        self._qr_stop_fg_color = "#f26d6d"
        self._qr_stop_hover_color = "#d95a5a"

        self._build_widgets()
        self._load_templates()
        self.refresh_recent_sessions()
        self._update_chrome_ui_state()
        self._schedule_chrome_state_poll()

    # ------------------------------------------------------------------
    # Automation hooks
    # ------------------------------------------------------------------
    def register_bonus_automation_handler(
        self,
        handler: Callable[[ChromeRemoteController], BonusAutomationResult],
    ) -> None:
        if handler in self._bonus_automation_handlers:
            return

        self._bonus_automation_handlers.append(handler)

        default_message = "System messages will appear here."

        if self._bonus_output_var.get() == default_message:
            handler_names = ", ".join(self._resolve_handler_name(h) for h in self._bonus_automation_handlers)
            self._bonus_output_var.set(
                f"Registered bonus automation workflows: {handler_names}" if handler_names else default_message
            )

    def set_chrome_controller(self, controller: ChromeRemoteController | None) -> None:
        if self._chrome_controller is controller:
            return

        self._chrome_controller = controller
        self._bonus_fetch_in_progress = False

        if controller is None:
            self._bonus_instruction_var.set(self._bonus_instruction_launch)
            self._bonus_output_var.set(self._chrome_inactive_message)

        self._update_chrome_ui_state(chrome_active=False)
        if self._chrome_state_poll_job is None:
            self._schedule_chrome_state_poll()

    def refresh_user_preferences(self) -> None:
        default_bonus = user_settings_store.get("default_bonus_points", settings.default_bonus_points)
        if default_bonus not in (None, "") and not self.bonus_point_var.get().strip():
            self.bonus_point_var.set(str(default_bonus))

    # ------------------------------------------------------------------
    # Status helpers
    # ------------------------------------------------------------------
    def _update_status_message(self, message: str, tone: str = "info") -> None:
        self._status_var.set(message)
        color_map = {
            "info": VS_TEXT_MUTED,
            "success": VS_SUCCESS,
            "warning": VS_WARNING,
        }
        if hasattr(self, "_status_label"):
            self._status_label.configure(text_color=color_map.get(tone, VS_TEXT_MUTED))

    def _set_manual_status(self, message: str, tone: str = "info") -> None:
        self._manual_status_var.set(message)
        color_map = {
            "info": VS_TEXT_MUTED,
            "success": VS_SUCCESS,
            "warning": VS_WARNING,
        }
        if hasattr(self, "_manual_status_label"):
            self._manual_status_label.configure(text_color=color_map.get(tone, VS_TEXT_MUTED))

    def _set_bonus_status(self, message: str, tone: str = "info") -> None:
        self._bonus_status_var.set(message)
        color_map = {
            "info": VS_TEXT_MUTED,
            "success": VS_SUCCESS,
            "warning": VS_WARNING,
        }
        if self._bonus_status_label is not None:
            self._bonus_status_label.configure(text_color=color_map.get(tone, VS_TEXT_MUTED))

    def _set_qr_status(self, message: str, tone: str = "info") -> None:
        self._qr_status_var.set(message)
        color_map = {
            "info": VS_TEXT_MUTED,
            "success": VS_SUCCESS,
            "warning": VS_WARNING,
        }
        if self._qr_status_label is not None:
            self._qr_status_label.configure(text_color=color_map.get(tone, VS_TEXT_MUTED))

    def _configure_qr_control(self, *, running: bool) -> None:
        if self._qr_control_button is None:
            return
        if running:
            self._qr_control_button.configure(
                state="normal",
                text="Stop scanner",
                fg_color=self._qr_stop_fg_color,
                hover_color=self._qr_stop_hover_color,
                text_color=VS_TEXT,
            )
        else:
            self._qr_control_button.configure(
                state="normal",
                text="Start scanner",
                fg_color=VS_ACCENT,
                hover_color=VS_ACCENT_HOVER,
                text_color=VS_TEXT,
            )

    def _set_qr_preview_border(self, color: str | None = None) -> None:
        if self._qr_preview_frame is None:
            return
        border_color = color or self._qr_default_border_color
        self._qr_preview_frame.configure(border_color=border_color)

    def _cancel_qr_border_reset(self) -> None:
        if self._qr_border_reset_job is None:
            return
        try:
            self.after_cancel(self._qr_border_reset_job)
        except Exception:
            pass
        finally:
            self._qr_border_reset_job = None

    def _schedule_qr_border_reset(self, delay_ms: int) -> None:
        self._cancel_qr_border_reset()
        if delay_ms <= 0:
            self._set_qr_preview_border(None)
            return
        if not self.winfo_exists():
            return
        self._qr_border_reset_job = self.after(delay_ms, self._reset_qr_preview_border)

    def _reset_qr_preview_border(self) -> None:
        self._qr_border_reset_job = None
        self._set_qr_preview_border(None)

    def _handle_auto_record_toggle(self) -> None:
        # Reset the last auto-record payload so the next scan can trigger a recording
        self._qr_last_auto_record_payload = None

    # ------------------------------------------------------------------
    # Layout construction
    # ------------------------------------------------------------------
    def _build_widgets(self) -> None:
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        container = ctk.CTkFrame(self, corner_radius=14, fg_color=VS_SURFACE)
        container.grid(row=0, column=0, padx=24, pady=24, sticky="nsew")
        container.grid_rowconfigure((0, 2), weight=1)
        container.grid_rowconfigure(1, weight=1)
        container.grid_columnconfigure((0, 2), weight=1)
        container.grid_columnconfigure(1, weight=1)

        self._session_form_frame = ctk.CTkFrame(container, corner_radius=12, fg_color=VS_SURFACE_ALT)
        self._session_form_frame.grid(row=1, column=1, padx=24, pady=24)
        self._session_form_frame.grid_columnconfigure(0, weight=1)
        self._build_session_form(self._session_form_frame)

        self._attendance_container = ctk.CTkFrame(container, fg_color=VS_SURFACE)
        self._attendance_container.grid(row=1, column=1, padx=24, pady=24, sticky="nsew")
        self._attendance_container.grid_remove()
        self._attendance_container.grid_rowconfigure(0, weight=0)
        self._attendance_container.grid_rowconfigure(1, weight=1)
        self._attendance_container.grid_columnconfigure(0, weight=3, uniform="attendance")
        self._attendance_container.grid_columnconfigure(1, weight=2, uniform="attendance")

        header_row = ctk.CTkFrame(self._attendance_container, fg_color=VS_SURFACE)
        header_row.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 18))
        header_row.grid_columnconfigure(0, weight=1)

        self._default_header_text = "Session activity"
        self._active_header = ctk.CTkLabel(
            header_row,
            text=self._default_header_text,
            font=ctk.CTkFont(size=24, weight="bold"),
            justify="left",
            text_color=VS_TEXT,
        )
        self._active_header.grid(row=0, column=0, sticky="w")

        self._end_session_button = ctk.CTkButton(
            header_row,
            text="End session",
            width=160,
            fg_color=VS_ACCENT,
            hover_color=VS_ACCENT_HOVER,
            text_color=VS_TEXT,
            command=self._handle_end_session,
        )
        self._end_session_button.grid(row=0, column=1, sticky="e")
        self._end_session_button.configure(state="disabled")

        self._tab_view = ctk.CTkTabview(
            self._attendance_container,
            fg_color=VS_SURFACE,
            segmented_button_fg_color=VS_SURFACE_ALT,
        )
        self._tab_view.grid(row=1, column=0, columnspan=2, sticky="nsew")
        self._tab_view.add("Record attendance")
        self._tab_view.add("Record bonus")

        attendance_tab = self._tab_view.tab("Record attendance")
        bonus_tab = self._tab_view.tab("Record bonus")

        segmented_button = self._tab_view._segmented_button
        segmented_button.configure(
            dynamic_resizing=False,
            width=440,
            height=46,
            corner_radius=18,
            fg_color=VS_DIVIDER,
            selected_color=VS_ACCENT,
            selected_hover_color=VS_ACCENT_HOVER,
            unselected_color=VS_SURFACE_ALT,
            unselected_hover_color=VS_DIVIDER,
            text_color=VS_TEXT,
            font=ctk.CTkFont(size=15, weight="bold"),
        )
        segmented_button.grid_configure(padx=72, pady=(6, 20), sticky="n")

        attendance_tab.grid_rowconfigure(0, weight=1)
        attendance_tab.grid_columnconfigure(0, weight=3, uniform="activity")
        attendance_tab.grid_columnconfigure(1, weight=2, uniform="activity")
        bonus_tab.grid_rowconfigure(0, weight=1)
        bonus_tab.grid_columnconfigure(0, weight=3, uniform="activity")
        bonus_tab.grid_columnconfigure(1, weight=2, uniform="activity")

        self._build_attendance_tab(attendance_tab)
        self._build_bonus_tab(bonus_tab)

    def _build_session_form(self, frame: ctk.CTkFrame) -> None:
        frame.grid_columnconfigure(0, weight=1)

        header_font = ctk.CTkFont(size=28, weight="bold")
        body_font = ctk.CTkFont(size=18)
        label_font = ctk.CTkFont(size=18, weight="bold")
        hint_font = ctk.CTkFont(size=14)

        header_row = ctk.CTkFrame(frame, fg_color="transparent")
        header_row.grid(row=0, column=0, padx=32, pady=(28, 12), sticky="ew")
        header_row.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header_row,
            text="Select session",
            font=header_font,
            text_color=VS_TEXT,
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkButton(
            header_row,
            text="Create new session",
            width=200,
            height=44,
            font=ctk.CTkFont(size=16, weight="bold"),
            fg_color=VS_ACCENT,
            hover_color=VS_ACCENT_HOVER,
            text_color=VS_TEXT,
            command=self._open_template_dialog,
        ).grid(row=0, column=1, sticky="e")

        template_card = ctk.CTkFrame(
            frame,
            corner_radius=18,
            fg_color=VS_SURFACE_ALT,
            border_width=1,
            border_color=VS_DIVIDER,
        )
        template_card.grid(row=1, column=0, padx=32, pady=(8, 20), sticky="ew")
        template_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            template_card,
            text="Session",
            font=label_font,
            text_color=VS_TEXT,
        ).grid(row=0, column=0, sticky="w", padx=24, pady=(20, 8))

        self.template_menu = ctk.CTkOptionMenu(
            template_card,
            values=[self.selected_template_label.get()],
            variable=self.selected_template_label,
            command=self._handle_template_select,
            fg_color=VS_BG,
            button_color=VS_ACCENT,
            button_hover_color=VS_ACCENT_HOVER,
            text_color=VS_TEXT,
            width=420,
            height=44,
            font=body_font,
        )
        self.template_menu.grid(row=1, column=0, padx=24, pady=(0, 16), sticky="ew")

        divider = ctk.CTkFrame(template_card, height=1, fg_color=VS_DIVIDER)
        divider.grid(row=2, column=0, padx=24, pady=4, sticky="ew")

        self._template_info_label = ctk.CTkLabel(
            template_card,
            text="No template selected",
            font=body_font,
            justify="left",
            text_color=VS_TEXT_MUTED,
            wraplength=520,
        )
        self._template_info_label.grid(row=3, column=0, padx=24, pady=(8, 20), sticky="w")

        form_card = ctk.CTkFrame(
            frame,
            corner_radius=18,
            fg_color=VS_SURFACE_ALT,
            border_width=1,
            border_color=VS_DIVIDER,
        )
        form_card.grid(row=2, column=0, padx=32, pady=(0, 16), sticky="ew")
        form_card.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkLabel(form_card, text="Chapter", font=label_font, text_color=VS_TEXT).grid(
            row=0, column=0, padx=24, pady=(20, 6), sticky="w"
        )
        chapter_entry = ctk.CTkEntry(
            form_card,
            textvariable=self.chapter_var,
            fg_color=VS_BG,
            border_color=VS_BORDER,
            text_color=VS_TEXT,
            placeholder_text="e.g. 6",
            placeholder_text_color=VS_TEXT_MUTED,
            font=body_font,
            height=42,
        )
        chapter_entry.grid(row=1, column=0, padx=24, pady=(0, 20), sticky="ew")

        ctk.CTkLabel(form_card, text="Week", font=label_font, text_color=VS_TEXT).grid(
            row=0, column=1, padx=24, pady=(20, 6), sticky="w"
        )
        week_menu = ctk.CTkOptionMenu(
            form_card,
            values=self.WEEK_OPTIONS,
            variable=self.week_var,
            fg_color=VS_BG,
            button_color=VS_ACCENT,
            button_hover_color=VS_ACCENT_HOVER,
            text_color=VS_TEXT,
            font=body_font,
            width=150,
            height=42,
        )
        week_menu.grid(row=1, column=1, padx=24, pady=(0, 20), sticky="ew")

        ctk.CTkLabel(
            form_card,
            text="Select a session and confirm the chapter/week to open a new attendance session.",
            font=hint_font,
            text_color=VS_TEXT_MUTED,
            justify="left",
            wraplength=520,
        ).grid(row=2, column=0, columnspan=2, padx=24, pady=(0, 20), sticky="w")

        self._status_label = ctk.CTkLabel(
            frame,
            textvariable=self._status_var,
            font=hint_font,
            text_color=VS_TEXT_MUTED,
        )
        self._status_label.grid(row=3, column=0, padx=32, pady=(4, 10), sticky="w")
        self._update_status_message(self._status_var.get())

        start_btn = ctk.CTkButton(
            frame,
            text="Start session",
            height=52,
            font=ctk.CTkFont(size=18, weight="bold"),
            command=self._handle_start_session,
            fg_color=VS_ACCENT,
            hover_color=VS_ACCENT_HOVER,
            text_color=VS_TEXT,
        )
        start_btn.grid(row=4, column=0, padx=32, pady=(4, 32), sticky="ew")

    def _build_attendance_tab(self, tab: ctk.CTkFrame) -> None:
        self._left_stack = ctk.CTkFrame(tab, fg_color=VS_SURFACE)
        self._left_stack.grid(row=0, column=0, sticky="nsew", padx=(12, 12), pady=(12, 12))
        self._left_stack.grid_columnconfigure(0, weight=1)
        self._left_stack.grid_rowconfigure(0, weight=1)
        self._left_stack.grid_rowconfigure(1, weight=2)

        self._manual_frame = ctk.CTkFrame(self._left_stack, corner_radius=12, fg_color=VS_SURFACE_ALT)
        self._manual_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 12))
        self._build_manual_panel(self._manual_frame)

        self._recent_frame = ctk.CTkFrame(self._left_stack, corner_radius=12, fg_color=VS_SURFACE_ALT)
        self._recent_frame.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        self._build_recent_panel(self._recent_frame)

        self._qr_frame = ctk.CTkFrame(tab, corner_radius=12, fg_color=VS_SURFACE_ALT)
        self._qr_frame.grid(row=0, column=1, sticky="nsew", padx=(12, 12), pady=(12, 12))
        self._build_qr_panel(self._qr_frame)

    def _build_bonus_tab(self, tab: ctk.CTkFrame) -> None:
        self._bonus_left_stack = ctk.CTkFrame(tab, fg_color=VS_SURFACE)
        self._bonus_left_stack.grid(row=0, column=0, sticky="nsew", padx=(12, 12), pady=(12, 12))
        self._bonus_left_stack.grid_columnconfigure(0, weight=1)
        self._bonus_left_stack.grid_rowconfigure(0, weight=1)
        self._bonus_left_stack.grid_rowconfigure(1, weight=2)

        self._bonus_manual_frame = ctk.CTkFrame(self._bonus_left_stack, corner_radius=12, fg_color=VS_SURFACE_ALT)
        self._bonus_manual_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 12))
        self._build_bonus_manual_panel(self._bonus_manual_frame)

        self._bonus_recent_frame = ctk.CTkFrame(self._bonus_left_stack, corner_radius=12, fg_color=VS_SURFACE_ALT)
        self._bonus_recent_frame.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        self._build_bonus_recent_panel(self._bonus_recent_frame)

        self._bonus_action_frame = ctk.CTkFrame(tab, corner_radius=12, fg_color=VS_SURFACE_ALT)
        self._bonus_action_frame.grid(row=0, column=1, sticky="nsew", padx=(12, 12), pady=(12, 12))
        self._build_bonus_action_panel(self._bonus_action_frame)

    def _build_recent_panel(self, frame: ctk.CTkFrame) -> None:
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(2, weight=1)

        header_font = ctk.CTkFont(size=20, weight="bold")
        label_font = ctk.CTkFont(size=18)
        preview_width = self._qr_preview_size[0]

        ctk.CTkLabel(frame, text="Recently logged students", font=header_font, text_color=VS_TEXT).grid(
            row=0, column=0, padx=20, pady=(20, 8), sticky="w"
        )

        toggle_row = ctk.CTkFrame(frame, fg_color=VS_SURFACE_ALT)
        toggle_row.grid(row=1, column=0, padx=20, pady=(0, 8), sticky="ew")
        toggle_row.grid_columnconfigure(0, weight=1)

        ctk.CTkSwitch(
            toggle_row,
            variable=self._hide_student_id_var,
            text="Hide student IDs",
            onvalue=True,
            offvalue=False,
            command=self.refresh_recent_sessions,
            font=label_font,
            text_color=VS_TEXT,
            progress_color=VS_ACCENT,
        ).grid(row=0, column=0, sticky="w")

        self._recent_list = ctk.CTkScrollableFrame(frame, label_text="", fg_color=VS_SURFACE_ALT)
        self._recent_list.grid(row=2, column=0, padx=20, pady=(0, 20), sticky="nsew")

    def _build_manual_panel(self, frame: ctk.CTkFrame) -> None:
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_columnconfigure(1, weight=1)

        header_font = ctk.CTkFont(size=20, weight="bold")
        label_font = ctk.CTkFont(size=18)
        status_font = ctk.CTkFont(size=15)

        header_row = ctk.CTkFrame(frame, fg_color=VS_SURFACE_ALT)
        header_row.grid(row=0, column=0, columnspan=2, padx=20, pady=(20, 12), sticky="ew")
        header_row.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(header_row, text="Manual entry", font=header_font, text_color=VS_TEXT).grid(
            row=0, column=0, sticky="w"
        )

        info = ctk.CTkLabel(frame, textvariable=self._session_info_var, text_color=VS_TEXT_MUTED, font=status_font)
        info.grid(row=1, column=0, columnspan=2, padx=20, pady=(0, 12), sticky="w")

        ctk.CTkLabel(frame, text="Student name", font=label_font, text_color=VS_TEXT).grid(
            row=2, column=0, padx=20, pady=6, sticky="w"
        )
        ctk.CTkEntry(
            frame,
            textvariable=self.student_name_var,
            font=label_font,
            fg_color=VS_BG,
            border_color=VS_BORDER,
            text_color=VS_TEXT,
            placeholder_text_color=VS_TEXT_MUTED,
        ).grid(row=2, column=1, padx=20, pady=6, sticky="ew")

        ctk.CTkLabel(frame, text="Student ID", font=label_font, text_color=VS_TEXT).grid(
            row=3, column=0, padx=20, pady=6, sticky="w"
        )
        ctk.CTkEntry(
            frame,
            textvariable=self.student_id_var,
            font=label_font,
            fg_color=VS_BG,
            border_color=VS_BORDER,
            text_color=VS_TEXT,
            placeholder_text_color=VS_TEXT_MUTED,
        ).grid(row=3, column=1, padx=20, pady=6, sticky="ew")

        frame.grid_rowconfigure(4, weight=1)

        button_row = ctk.CTkFrame(frame, fg_color=VS_SURFACE_ALT)
        button_row.grid(row=5, column=0, columnspan=2, padx=20, pady=(0, 20), sticky="ew")
        button_row.grid_columnconfigure(0, weight=1)
        button_row.grid_columnconfigure(1, weight=0)
        button_row.grid_columnconfigure(2, weight=0)

        self._manual_status_label = ctk.CTkLabel(
            button_row,
            textvariable=self._manual_status_var,
            text_color=VS_TEXT_MUTED,
            font=status_font,
        )
        self._manual_status_label.grid(row=0, column=0, sticky="w")
        self._set_manual_status(self._manual_status_var.get())

        ctk.CTkButton(
            button_row,
            text="Record attendance",
            command=self._handle_manual_record,
            width=220,
            fg_color=VS_ACCENT,
            hover_color=VS_ACCENT_HOVER,
            text_color=VS_TEXT,
        ).grid(row=0, column=2, sticky="e")

    def _build_qr_panel(self, frame: ctk.CTkFrame) -> None:
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(2, weight=1)
        header_font = ctk.CTkFont(size=20, weight="bold")
        body_font = ctk.CTkFont(size=15)
        message_font = ctk.CTkFont(size=18, weight="normal")
        preview_width = self._qr_preview_size[0]

        header_row = ctk.CTkFrame(frame, fg_color=VS_SURFACE_ALT)
        header_row.grid(row=0, column=0, padx=20, pady=(20, 12), sticky="ew")
        header_row.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(header_row, text="QR scanner", font=header_font, text_color=VS_TEXT).grid(
            row=0, column=0, sticky="w"
        )

        self._qr_control_button = ctk.CTkButton(
            header_row,
            text="Start scanner",
            command=self._handle_toggle_qr_scanner,
            width=200,
            fg_color=VS_ACCENT,
            hover_color=VS_ACCENT_HOVER,
            text_color=VS_TEXT,
        )
        self._qr_control_button.grid(row=0, column=1, sticky="e")
        self._qr_control_button.configure(state="normal")

        ctk.CTkLabel(
            frame,
            text=(
                "Use the scanner to capture student IDs from QR codes. "
            ),
            justify="left",
            wraplength=preview_width,
            font=body_font,
            text_color=VS_TEXT_MUTED,
        ).grid(row=1, column=0, padx=20, pady=(0, 12), sticky="w")

        preview_container = ctk.CTkFrame(frame, fg_color="transparent")
        preview_container.grid(row=2, column=0, padx=20, pady=(0, 16), sticky="nsew")
        preview_container.grid_columnconfigure(0, weight=1)
        preview_container.grid_rowconfigure(0, weight=1)

        preview_card = ctk.CTkFrame(preview_container, corner_radius=16, fg_color=VS_CARD)
        preview_card.grid(row=0, column=0, sticky="nsew")
        preview_card.grid_columnconfigure(0, weight=1)
        preview_card.grid_rowconfigure(1, weight=1)

        self._qr_status_label = ctk.CTkLabel(
            preview_card,
            textvariable=self._qr_status_var,
            text_color=VS_TEXT,
            font=message_font,
            justify="center",
            wraplength=preview_width,
        )
        self._qr_status_label.grid(row=0, column=0, padx=16, pady=(18, 8), sticky="ew")

        self._qr_preview_frame = ctk.CTkFrame(
            preview_card,
            corner_radius=18,
            fg_color=VS_SURFACE_ALT,
            border_width=3,
            border_color=self._qr_default_border_color,
        )
        self._qr_preview_frame.grid(row=1, column=0, padx=16, pady=(0, 16), sticky="nsew")
        self._qr_preview_frame.grid_propagate(False)
        self._qr_preview_frame.configure(width=self._qr_preview_size[0], height=self._qr_preview_size[1])

        self._qr_preview_label = ctk.CTkLabel(
            self._qr_preview_frame,
            text="Camera preview inactive",
            text_color=VS_TEXT_MUTED,
            font=ctk.CTkFont(size=16),
            justify="center",
            image=self._qr_preview_placeholder,
            compound="center",
        )
        self._qr_preview_label.pack(expand=True, fill="both", padx=12, pady=12)

        self._qr_auto_record_switch = ctk.CTkSwitch(
            preview_card,
            text="Auto-record attendance",
            variable=self._qr_auto_record_var,
            command=self._handle_auto_record_toggle,
            onvalue=True,
            offvalue=False,
        )
        self._qr_auto_record_switch.grid(row=2, column=0, padx=18, pady=(0, 18), sticky="w")

        ctk.CTkLabel(
            frame,
            text="Keep the QR code within the frame. You'll see the details fill in automatically when detected.",
            justify="left",
            wraplength=preview_width,
            font=body_font,
            text_color=VS_TEXT_MUTED,
        ).grid(row=3, column=0, padx=20, pady=(0, 12), sticky="w")

        self._configure_qr_control(running=False)
        self._set_qr_status(self._qr_status_var.get())

    def _build_bonus_manual_panel(self, frame: ctk.CTkFrame) -> None:
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_columnconfigure(1, weight=1)

        header_font = ctk.CTkFont(size=20, weight="bold")
        label_font = ctk.CTkFont(size=18)
        status_font = ctk.CTkFont(size=15)

        header_row = ctk.CTkFrame(frame, fg_color=VS_SURFACE_ALT)
        header_row.grid(row=0, column=0, columnspan=2, padx=20, pady=(20, 12), sticky="ew")
        header_row.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(header_row, text="Manual bonus entry", font=header_font, text_color=VS_TEXT).grid(
            row=0, column=0, sticky="w"
        )

        info = ctk.CTkLabel(frame, textvariable=self._bonus_info_var, text_color=VS_TEXT_MUTED, font=status_font)
        info.grid(row=1, column=0, columnspan=2, padx=20, pady=(0, 12), sticky="w")

        ctk.CTkLabel(frame, text="Student name", font=label_font, text_color=VS_TEXT).grid(
            row=2, column=0, padx=20, pady=6, sticky="w"
        )
        ctk.CTkEntry(
            frame,
            textvariable=self.bonus_student_name_var,
            font=label_font,
            fg_color=VS_BG,
            border_color=VS_BORDER,
            text_color=VS_TEXT,
            placeholder_text_color=VS_TEXT_MUTED,
        ).grid(row=2, column=1, padx=20, pady=6, sticky="ew")

        ctk.CTkLabel(frame, text="Bonus point", font=label_font, text_color=VS_TEXT).grid(
            row=3, column=0, padx=20, pady=6, sticky="w"
        )
        ctk.CTkEntry(
            frame,
            textvariable=self.bonus_point_var,
            font=label_font,
            fg_color=VS_BG,
            border_color=VS_BORDER,
            text_color=VS_TEXT,
            placeholder_text_color=VS_TEXT_MUTED,
        ).grid(row=3, column=1, padx=20, pady=6, sticky="ew")

        frame.grid_rowconfigure(4, weight=1)

        button_row = ctk.CTkFrame(frame, fg_color=VS_SURFACE_ALT)
        button_row.grid(row=5, column=0, columnspan=2, padx=20, pady=(0, 20), sticky="ew")
        button_row.grid_columnconfigure(0, weight=1)
        button_row.grid_columnconfigure(1, weight=0)

        self._bonus_status_label = ctk.CTkLabel(
            button_row,
            textvariable=self._bonus_status_var,
            text_color=VS_TEXT_MUTED,
            font=status_font,
        )
        self._bonus_status_label.grid(row=0, column=0, sticky="w")
        self._set_bonus_status(self._bonus_status_var.get())

        ctk.CTkButton(
            button_row,
            text="Record bonus",
            command=self._handle_bonus_record,
            width=220,
            fg_color=VS_ACCENT,
            hover_color=VS_ACCENT_HOVER,
            text_color=VS_TEXT,
        ).grid(row=0, column=1, sticky="e")

    def _build_bonus_recent_panel(self, frame: ctk.CTkFrame) -> None:
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(1, weight=1)

        header_font = ctk.CTkFont(size=20, weight="bold")
        body_font = ctk.CTkFont(size=16)

        ctk.CTkLabel(frame, text="Bonuses in this session", font=header_font, text_color=VS_TEXT).grid(
            row=0, column=0, padx=20, pady=(20, 8), sticky="w"
        )

        self._bonus_recent_list = ctk.CTkScrollableFrame(frame, label_text="", fg_color=VS_SURFACE_ALT)
        self._bonus_recent_list.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="nsew")

        empty_label = ctk.CTkLabel(
            self._bonus_recent_list,
            text="No bonus points awarded yet.",
            text_color=VS_TEXT_MUTED,
            font=body_font,
        )
        empty_label.pack(anchor="w", padx=12, pady=6)

    def _build_bonus_action_panel(self, frame: ctk.CTkFrame) -> None:
        frame.grid_columnconfigure((0, 1), weight=1)
        frame.grid_rowconfigure(4, weight=1)

        header_font = ctk.CTkFont(size=20, weight="bold")
        body_font = ctk.CTkFont(size=15)
        header_row = ctk.CTkFrame(frame, fg_color=VS_SURFACE_ALT)
        header_row.grid(row=0, column=0, columnspan=2, padx=20, pady=(20, 8), sticky="ew")
        header_row.grid_columnconfigure(0, weight=1)
        header_row.grid_columnconfigure(1, weight=0)

        ctk.CTkLabel(header_row, text="Automation", font=header_font, text_color=VS_TEXT).grid(
            row=0, column=0, sticky="w"
        )

        open_chrome_button = ctk.CTkButton(
            header_row,
            text="Open Chrome",
            command=lambda: self._handle_open_chrome(source="bonus"),
            width=140,
            fg_color=VS_SURFACE_ALT if not self._chrome_controller else VS_ACCENT,
            hover_color=VS_ACCENT_HOVER if self._chrome_controller else VS_DIVIDER,
            text_color=VS_TEXT,
            image=self._chrome_icon,
            compound="left",
        )
        open_chrome_button.grid(row=0, column=1, sticky="e")
        if not self._chrome_controller:
            open_chrome_button.configure(state="disabled")
        if open_chrome_button not in self._chrome_buttons:
            self._chrome_buttons.append(open_chrome_button)
        self._bonus_open_chrome_button = open_chrome_button

        instruction_label = ctk.CTkLabel(
            frame,
            textvariable=self._bonus_instruction_var,
            justify="left",
            font=body_font,
            text_color=VS_TEXT_MUTED,
            wraplength=520,
        )
        instruction_label.grid(row=1, column=0, columnspan=2, padx=20, pady=(0, 12), sticky="w")

        get_student_button = ctk.CTkButton(
            frame,
            text="Get student data",
            command=self._handle_bonus_get_student_data,
            width=200,
            fg_color=VS_SURFACE_ALT if not self._chrome_controller else VS_ACCENT,
            hover_color=VS_ACCENT_HOVER if self._chrome_controller else VS_DIVIDER,
            text_color=VS_TEXT,
        )
        get_student_button.grid(row=2, column=0, columnspan=2, padx=20, pady=(0, 12), sticky="ew")
        if not self._chrome_controller:
            get_student_button.configure(state="disabled")
        self._bonus_get_student_button = get_student_button

        student_card = ctk.CTkFrame(
            frame,
            corner_radius=12,
            fg_color=VS_CARD,
            border_width=1,
            border_color=VS_DIVIDER,
        )
        student_card.grid(row=3, column=0, columnspan=2, padx=20, pady=(0, 12), sticky="nsew")
        student_card.grid_columnconfigure(0, weight=1)
        student_card.grid_columnconfigure(1, weight=0)
        self._bonus_student_card = student_card

        name_font = ctk.CTkFont(size=19, weight="bold")
        meta_font = ctk.CTkFont(size=15)
        grade_font = ctk.CTkFont(size=15, weight="bold")

        self._bonus_student_name_label = ctk.CTkLabel(
            student_card,
            textvariable=self._bonus_student_name_display,
            font=name_font,
            text_color=VS_TEXT,
            justify="left",
            wraplength=320,
        )
        self._bonus_student_name_label.grid(row=0, column=0, sticky="w", padx=16, pady=(16, 6))

        self._bonus_student_grade_label = ctk.CTkLabel(
            student_card,
            textvariable=self._bonus_student_grade_display,
            font=grade_font,
            text_color=VS_BG,
            fg_color=VS_ACCENT,
            corner_radius=8,
            padx=12,
            pady=4,
            justify="center",
        )
        self._bonus_student_grade_label.grid(row=0, column=1, sticky="ne", padx=(0, 16), pady=(16, 6))

        self._bonus_student_task_label = ctk.CTkLabel(
            student_card,
            textvariable=self._bonus_student_task_display,
            font=meta_font,
            text_color=VS_TEXT,
            justify="left",
            wraplength=320,
        )
        self._bonus_student_task_label.grid(row=1, column=0, columnspan=2, sticky="w", padx=16, pady=(0, 2))

        self._bonus_student_time_label = ctk.CTkLabel(
            student_card,
            textvariable=self._bonus_student_time_display,
            font=meta_font,
            text_color=VS_TEXT_MUTED,
            justify="left",
            wraplength=320,
        )
        self._bonus_student_time_label.grid(row=2, column=0, columnspan=2, sticky="w", padx=16, pady=(0, 4))

        self._bonus_student_file_chip = ctk.CTkLabel(
            student_card,
            textvariable=self._bonus_student_file_display,
            font=meta_font,
            text_color=VS_TEXT,
            fg_color=VS_SURFACE_ALT,
            corner_radius=8,
            padx=12,
            pady=4,
            justify="left",
        )
        self._bonus_student_file_chip.grid(row=3, column=0, columnspan=2, sticky="w", padx=16, pady=(8, 16))

        self._bonus_student_grade_label.grid_remove()
        self._bonus_student_file_chip.grid_remove()
        student_card.grid_remove()

        self._bonus_output_label = ctk.CTkLabel(
            frame,
            textvariable=self._bonus_output_var,
            text_color=VS_TEXT_MUTED,
            justify="left",
            wraplength=520,
        )
        self._bonus_output_label.grid(row=5, column=0, columnspan=2, padx=20, pady=(0, 20), sticky="sw")

    def refresh_recent_sessions(self) -> None:
        self._refresh_recent_attendance()
        self._refresh_bonus_list()

    def _refresh_bonus_list(self) -> None:
        if self._bonus_recent_list is None:
            return

        for widget in self._bonus_recent_list.winfo_children():
            widget.destroy()

        if not self._active_session_id:
            ctk.CTkLabel(
                self._bonus_recent_list,
                text="Start a session to record bonus points.",
                text_color=VS_TEXT_MUTED,
            ).pack(anchor="w", padx=12, pady=6)
            return

        records = self._service.list_bonus_for_session(self._active_session_id, limit=8)
        if not records:
            ctk.CTkLabel(
                self._bonus_recent_list,
                text="No bonus points awarded yet.",
                text_color=VS_TEXT_MUTED,
            ).pack(anchor="w", padx=12, pady=6)
            return

        name_font = ctk.CTkFont(size=18, weight="bold")
        point_font = ctk.CTkFont(size=16)

        for record in records:
            card = ctk.CTkFrame(self._bonus_recent_list, corner_radius=10, fg_color=VS_CARD)
            card.pack(fill="x", padx=12, pady=6)
            card.grid_columnconfigure(0, weight=1)
            card.grid_columnconfigure(1, weight=0)

            name_label = ctk.CTkLabel(
                card,
                text=record.get("student_name", ""),
                font=name_font,
                text_color=VS_TEXT,
                justify="left",
            )
            name_label.grid(row=0, column=0, sticky="w", padx=12, pady=10)

            point_label = ctk.CTkLabel(
                card,
                text=f"{int(record.get('b_point', 0) or 0)} pts",
                font=point_font,
                text_color=VS_ACCENT,
            )
            point_label.grid(row=0, column=1, sticky="e", padx=(4, 12), pady=10)

    # ------------------------------------------------------------------
    # Session template management
    # ------------------------------------------------------------------
    def _load_templates(self) -> None:
        self._templates = self._service.list_session_templates()
        if not self._templates:
            self.template_menu.configure(values=["No sessions"], state="disabled")
            self.selected_template_label.set("No sessions")
            self._template_info_label.configure(text="Create a session to begin.")
            return

        values = [template.display_label() for template in self._templates]
        self.template_menu.configure(values=values, state="normal")

        first_label = values[0]
        self.selected_template_label.set(first_label)
        self.template_menu.set(first_label)
        self._handle_template_select(first_label)

    def _handle_template_select(self, choice: str) -> None:
        for template in self._templates:
            if template.display_label() == choice:
                self.selected_template_id.set(template.id)
                self.selected_template_label.set(choice)
                self._template_info_label.configure(
                    text=(
                        f"{template.weekday_label()} · {template.start_hour:02d}-{template.end_hour:02d}\n"
                        f"{template.campus_name}\n"
                        f"Room {template.room_code}"
                    )
                )
                return

    def _open_template_dialog(self) -> None:
        dialog = TemplateDialog(self, self._service)
        dialog.grab_set()

    # ------------------------------------------------------------------
    # Session lifecycle handlers
    # ------------------------------------------------------------------
    def _handle_start_session(self) -> None:
        template_id = self.selected_template_id.get()
        chapter = self.chapter_var.get().strip()
        week_value = self.week_var.get()

        if template_id <= 0:
            self._update_status_message("Select a session first.", tone="warning")
            return

        if not chapter or not week_value:
            self._update_status_message("Chapter and week are required.", tone="warning")
            return

        template = self._service.get_session_template(template_id)
        if not template:
            self._update_status_message("Session not found. Create a new one.", tone="warning")
            return

        session = AttendanceSession(
            chapter_code=chapter,
            week_number=int(week_value),
            weekday_index=template.weekday_index,
            start_hour=template.start_hour,
            end_hour=template.end_hour,
            campus_name=template.campus_name,
            room_code=template.room_code,
        )

        try:
            session_id = self._service.start_session(session)
        except DuplicateSessionError:
            messagebox.showwarning("Duplicate session", "A session with these details already exists.")
            self._update_status_message("Duplicate session detected.", tone="warning")
            return
        except Exception as exc:  # pragma: no cover - guard unexpected issues
            messagebox.showerror("Error", f"Failed to start session: {exc}")
            self._update_status_message("Failed to start session.", tone="warning")
            return

        self._activate_session(session, session_id)
        if self._on_session_started:
            self._on_session_started()

    def _handle_end_session(self) -> None:
        self._active_session_id = None
        self._session_info_var.set("")
        self._bonus_info_var.set("")
        self.student_name_var.set("")
        self.student_id_var.set("")
        self.bonus_student_name_var.set("")
        self.bonus_point_var.set("")
        if self._qr_scanner.is_running:
            self._stop_qr_scanner()
        else:
            self._set_qr_status("Scanner idle")
            self._configure_qr_control(running=False)
            if self._qr_preview_label is not None:
                self._qr_preview_label.configure(image=self._qr_preview_placeholder, text="Camera preview inactive")
            self._qr_preview_image = None
            self._qr_preview_busy = False
            self._set_qr_preview_border(None)
        self._qr_last_auto_record_payload = None
        self._set_manual_status("")
        self._set_bonus_status("")
        self._bonus_instruction_var.set(self._bonus_instruction_launch)
        self._bonus_student_details_var.set("")
        self._update_bonus_student_card(None)
        self._bonus_output_var.set("System messages will appear here.")
        self._bonus_fetch_in_progress = False
        self._update_chrome_ui_state()
        self._set_qr_status("Scanner idle")
        self._configure_qr_control(running=False)
        if self._qr_preview_label is not None:
            self._qr_preview_label.configure(image=self._qr_preview_placeholder, text="Camera preview inactive")
        self._qr_preview_image = None
        self._qr_preview_busy = False
        self._set_qr_preview_border(None)
        self._qr_preview_busy = False
        if hasattr(self, "_active_header"):
            self._active_header.configure(text=self._default_header_text)
        if hasattr(self, "_end_session_button"):
            self._end_session_button.configure(state="disabled")
        self._show_session_form()
        if self._on_session_ended:
            self._on_session_ended()
        self.refresh_recent_sessions()

    def _activate_session(self, session: AttendanceSession, session_id: int) -> None:
        self._active_session_id = session_id
        self._session_info_var.set(
            (
                f"Chapter {session.chapter_code} "
                f"Week {session.week_number}\n"
            )
        )
        self._update_status_message(f"Session started. Ready for attendance.", tone="success")
        self._bonus_info_var.set(
            (
                f"Chapter {session.chapter_code} · Week {session.week_number}\n"
            )
        )
        self._set_bonus_status("Ready to record bonus points.")
        self._bonus_instruction_var.set(self._bonus_instruction_launch)
        self._bonus_student_details_var.set("")
        self._update_bonus_student_card(None)
        self._bonus_output_var.set("System messages will appear here.")
        self._bonus_fetch_in_progress = False
        self._update_chrome_ui_state()
        if hasattr(self, "_active_header"):
            weekday_name = next(
                (label for label, index in WEEKDAY_OPTIONS if index == session.weekday_index),
                f"Day {session.weekday_index}",
            )
            self._active_header.configure(
                text=(
                    f"{weekday_name} {session.start_hour:02d}-{session.end_hour:02d}"
                    f" — {session.campus_name} · {session.room_code}"
                )
            )
        if hasattr(self, "_end_session_button"):
            self._end_session_button.configure(state="normal")
        self._show_attendance_ui()
        self.refresh_recent_sessions()

    def _show_session_form(self) -> None:
        self._attendance_container.grid_remove()
        self._session_form_frame.grid()
        self._update_status_message("Choose a session to get started.")
        if hasattr(self, "_active_header"):
            self._active_header.configure(text=self._default_header_text)
        if hasattr(self, "_end_session_button"):
            self._end_session_button.configure(state="disabled")

    def _show_attendance_ui(self) -> None:
        self._session_form_frame.grid_remove()
        self._attendance_container.grid()

    # ------------------------------------------------------------------
    # Manual attendance workflow
    # ------------------------------------------------------------------
    def _handle_open_chrome(self, *, source: str = "attendance") -> None:
        status_setter = self._set_bonus_status if source == "bonus" else self._set_manual_status

        if not self._chrome_controller:
            status_setter("Chrome automation is not configured.", tone="warning")
            return

        for button in self._chrome_buttons:
            button.configure(state="disabled")

        status_setter("Opening automated Chrome...", tone="info")
        if source == "bonus":
            self._bonus_instruction_var.set(self._bonus_instruction_launch)
            self._bonus_student_details_var.set("")
            self._update_bonus_student_card(None)
            self._bonus_output_var.set("Opening automated Chrome...")

        threading.Thread(target=self._open_chrome_async, args=(source,), daemon=True).start()

    def _handle_toggle_qr_scanner(self) -> None:
        if self._qr_scanner.is_running:
            self._stop_qr_scanner()
        else:
            self._start_qr_scanner()

    def _open_chrome_async(self, source: str) -> None:
        if not self._chrome_controller:
            return

        try:
            self._chrome_controller.open_browser()
        except ChromeAutomationError as exc:
            message = str(exc)
            tone = "warning"
        except Exception as exc:  # pragma: no cover - guard unexpected issues
            message = f"Failed to open Chrome: {exc}"
            tone = "warning"
        else:
            message = self._chrome_ready_message
            tone = "success"

        def _finalize() -> None:
            status_setter = self._set_bonus_status if source == "bonus" else self._set_manual_status
            status_setter(message, tone)
            state = "normal" if self._chrome_controller else "disabled"
            for button in self._chrome_buttons:
                button.configure(state=state)

            if source == "bonus":
                if tone == "success":
                    self._bonus_instruction_var.set(self._bonus_instruction_ready)
                    self._bonus_output_var.set(self._chrome_ready_message)
                    if self._bonus_automation_handlers:
                        threading.Thread(target=self._execute_bonus_handlers, daemon=True).start()
                else:
                    self._bonus_instruction_var.set(self._bonus_instruction_launch)
                    self._bonus_output_var.set("Automation aborted due to Chrome launch failure.")

            self._update_chrome_ui_state()

        self.after(0, _finalize)

    def _handle_bonus_get_student_data(self) -> None:
        if not self._chrome_controller:
            # self._set_bonus_status("Chrome automation is not configured.", tone="warning")
            return

        self._bonus_fetch_in_progress = True
        if self._bonus_get_student_button is not None:
            self._bonus_get_student_button.configure(state="disabled")

        self._set_bonus_status("Fetching student data...", tone="info")
        self._bonus_student_details_var.set("")
        self._update_bonus_student_card(None)
        self._bonus_output_var.set("Fetching student data...")
        self._update_chrome_ui_state()

        threading.Thread(target=self._fetch_bonus_student_data_async, daemon=True).start()

    def _fetch_bonus_student_data_async(self) -> None:
        controller = self._chrome_controller
        if controller is None:
            return

        error_message: str | None = None
        payload: dict[str, object] | None = None

        try:
            controller.open_browser()
            result = get_bonus_student_data(controller)
            if isinstance(result, BonusAutomationResult):
                if result.success:
                    payload = dict(result.payload or {})
                else:
                    error_message = result.summary or "Automation workflow failed."
            else:
                error_message = "Automation returned an unexpected response."
        except Exception as exc:  # pragma: no cover - guard automation issues
            error_message = str(exc)

        def _finalize() -> None:
            self._bonus_fetch_in_progress = False

            if error_message:
                self._set_bonus_status("Failed to fetch student data.", tone="warning")
                self._bonus_output_var.set(f"Failed to fetch student data: {error_message}")
                self._bonus_student_details_var.set("")
                self._update_bonus_student_card(None)
                self._update_chrome_ui_state()
                return

            if payload:
                student_name_value = payload.get("student_name")
                if isinstance(student_name_value, str) and student_name_value.strip():
                    normalized = student_name_value.strip()
                    self.bonus_student_name_var.set(normalized)
                default_points = user_settings_store.get("default_bonus_points", settings.default_bonus_points)
                if default_points not in (None, ""):
                    self.bonus_point_var.set(str(default_points))

                details_text = self._format_bonus_student_details(payload)
                self._bonus_student_details_var.set(details_text)
                self._update_bonus_student_card(payload)
                self._bonus_output_var.set("Student data captured successfully.")
                self._set_bonus_status("Student data captured.", tone="success")
            else:
                self._bonus_student_details_var.set("")
                self._update_bonus_student_card(None)
                self._set_bonus_status("No student data returned.", tone="warning")
                self._bonus_output_var.set("No student data returned from automation.")

            self._update_chrome_ui_state()

        self.after(0, _finalize)

    def _execute_bonus_handlers(self) -> None:
        handlers = list(self._bonus_automation_handlers)
        controller = self._chrome_controller

        if not handlers:
            def _no_handlers() -> None:
                self._bonus_output_var.set("No bonus automation workflows registered.")
                # self._set_bonus_status("No automation workflows to run.")

            self.after(0, _no_handlers)
            return

        if controller is None:
            def _missing_controller() -> None:
                self._bonus_output_var.set("Chrome controller is unavailable.")
                # self._set_bonus_status("Chrome automation is not configured.", tone="warning")

            self.after(0, _missing_controller)
            return

        def _announce_start() -> None:
            # self._set_bonus_status("Running bonus automation workflows...", tone="info")
            self._bonus_output_var.set("Running bonus automation workflows...")

        self.after(0, _announce_start)

        results: list[BonusAutomationResult] = []

        for handler in handlers:
            handler_name = self._resolve_handler_name(handler)
            try:
                result = handler(controller)
            except Exception as exc:  # pragma: no cover - guard automation issues
                result = BonusAutomationResult(
                    handler_name=handler_name,
                    success=False,
                    summary="Workflow raised an exception.",
                    details=str(exc),
                )
            else:
                if not isinstance(result, BonusAutomationResult):
                    result = BonusAutomationResult(
                        handler_name=handler_name,
                        success=False,
                        summary="Workflow returned an unsupported result type.",
                        details=f"Expected BonusAutomationResult, got {type(result).__name__} instead.",
                    )
            results.append(result)

        def _render_results() -> None:
            if not results:
                self._bonus_output_var.set("No bonus automation workflows produced output.")
                # self._set_bonus_status("No automation output received.")
                return

            success_count = sum(1 for res in results if res.success)
            failure_count = sum(1 for res in results if not res.success)

            formatted: list[str] = []
            for res in results:
                indicator = "✅" if res.success else "⚠️"
                formatted.append(f"{indicator}: {res.summary}")
                if res.details:
                    for line in res.details.splitlines():
                        line = line.strip()
                        if line:
                            formatted.append(f"    • {line}")

            self._bonus_output_var.set("\n".join(formatted))

        self.after(0, _render_results)

    def _record_attendance_entry(
        self,
        *,
        source: str,
    ) -> tuple[bool, str, str, Optional[str], Optional[str]]:
        if not self._active_session_id:
            return False, "Start a session before recording attendance.", "warning", None, "no-session"

        student_code = self.student_id_var.get().strip()
        if not student_code:
            return False, "Student ID is required.", "warning", None, "missing-id"

        student_name = self.student_name_var.get().strip()
        if student_name:
            parts = student_name.split(" ")
            first_name = parts[0]
            last_name = " ".join(parts[1:]) if len(parts) > 1 else None
        else:
            first_name = None
            last_name = None

        student = Student(
            student_code=student_code,
            first_name=first_name,
            last_name=last_name,
        )

        try:
            self._service.record_attendance(self._active_session_id, student, source=source)
        except DuplicateAttendanceError:
            return False, f"{student_code} is already logged for this session.", "warning", student_code, "duplicate"
        except Exception as exc:  # pragma: no cover - guard unexpected issues
            return False, f"Failed to record attendance: {exc}", "warning", student_code, "error"

        self.refresh_recent_sessions()
        return True, f"Recorded {student_name}", "success", student_code, None

    def _handle_manual_record(self) -> None:
        self._set_manual_status("")
        success, message, tone, _, _ = self._record_attendance_entry(source="manual")
        self._set_manual_status(message, tone=tone)
        if success:
            self.student_id_var.set("")
            self.student_name_var.set("")

    def _handle_bonus_record(self) -> None:
        self._set_bonus_status("")

        if not self._active_session_id:
            self._set_bonus_status("Start a session before recording bonus points.", tone="warning")
            return

        student_name = self.bonus_student_name_var.get().strip()
        bonus_value_raw = self.bonus_point_var.get().strip()

        if not student_name:
            self._set_bonus_status("Student name is required.", tone="warning")
            return

        try:
            bonus_value = int(bonus_value_raw)
        except ValueError:
            self._set_bonus_status("Enter a whole number of bonus points.", tone="warning")
            return

        bonus_record = BonusRecord(
            session_id=self._active_session_id,
            student_name=student_name,
            b_point=bonus_value,
            status="recorded",
        )

        try:
            self._service.record_bonus(bonus_record)
        except Exception as exc:  # pragma: no cover - guard unexpected issues
            self._set_bonus_status(f"Failed to record bonus: {exc}", tone="warning")
            return

        self.bonus_student_name_var.set("")
        self.bonus_point_var.set("")
        self._set_bonus_status(f"Recorded bonus for {student_name}.", tone="success")
        self.refresh_recent_sessions()

    def _start_qr_scanner(self) -> None:
        if self._qr_control_button is not None:
            self._qr_control_button.configure(state="disabled")
        self._set_qr_status("Starting scanner…")
        self._cancel_qr_border_reset()
        self._set_qr_preview_border(None)
        if self._qr_preview_label is not None:
            self._qr_preview_label.configure(image=self._qr_preview_placeholder, text="Camera preview inactive")
        self._qr_preview_image = None
        self._qr_last_auto_record_payload = None

        def _start() -> None:
            def _on_payload(payload: str) -> None:
                self.after(0, lambda: self._handle_qr_payload(payload))

            def _on_error(message: str) -> None:
                self.after(0, lambda: self._handle_qr_error(message))

            def _on_frame(frame: Any) -> None:
                self.after(0, lambda f=frame: self._handle_qr_frame(f))

            started = self._qr_scanner.start(_on_payload, on_error=_on_error, on_frame=_on_frame)

            def _finalize() -> None:
                if not self.winfo_exists():
                    return
                if not started:
                    if self._qr_status_var.get() in ("Starting scanner…", "Scanner idle"):
                        self._set_qr_status("Scanner unavailable.", tone="warning")
                    self._configure_qr_control(running=False)
                    self._set_qr_preview_border(None)
                    return

                self._configure_qr_control(running=True)
                if self._qr_preview_label is not None:
                    self._qr_preview_label.configure(image=self._qr_preview_placeholder, text="Waiting for camera…")
                self._set_qr_preview_border(None)
                self._set_qr_status("Scanner active", tone="success")

            self.after(0, _finalize)

        threading.Thread(target=_start, daemon=True).start()

    def _stop_qr_scanner(self) -> None:
        if self._qr_control_button is not None:
            self._qr_control_button.configure(state="disabled")
        self._set_qr_status("Stopping scanner…")

        def _stop() -> None:
            self._qr_scanner.stop()

            def _finalize() -> None:
                if not self.winfo_exists():
                    return
                self._configure_qr_control(running=False)
                if self._qr_status_var.get() == "Stopping scanner…":
                    self._set_qr_status("Scanner idle")
                if self._qr_preview_label is not None:
                    self._qr_preview_label.configure(image=self._qr_preview_placeholder, text="Camera preview inactive")
                self._qr_preview_image = None
                self._qr_preview_busy = False
                self._cancel_qr_border_reset()
                self._qr_last_auto_record_payload = None
                self._set_qr_preview_border(None)

            self.after(0, _finalize)

        threading.Thread(target=_stop, daemon=True).start()

    def _attempt_auto_record(self, payload: str) -> None:
        if not self._qr_auto_record_var.get():
            return
        if self._qr_last_auto_record_payload == payload:
            return

        success, message, tone, student_code, error_code = self._record_attendance_entry(source="qr-auto")

        if success:
            self._qr_last_auto_record_payload = payload
            if student_code:
                self._set_qr_status(f"Auto-recorded: {message.strip('Recorded ')} | {student_code}", tone="success")
            self._set_manual_status(message, tone=tone)
            return

        if error_code == "duplicate":
            self._qr_last_auto_record_payload = payload

        if message:
            self._set_qr_status(message, tone=tone)
            self._set_manual_status(message, tone=tone)

    def _handle_qr_payload(self, payload: str) -> None:
        normalized = payload.strip()
        if not normalized:
            return

        now = time.time()

        if self._qr_last_payload == normalized and (now - self._qr_last_scan_time) < self._qr_debounce_seconds:
            return

        cleaned = normalized

        name_value: Optional[str] = None
        student_code: Optional[str] = None

        if "|" in cleaned:
            code_part, name_part = cleaned.split("|", 1)
            name_value = name_part.strip() or None
            student_code = code_part.strip() or None
        else:
            student_code = cleaned

        if not student_code:
            self._set_qr_status("QR code missing student ID.", tone="warning")
            self._set_qr_preview_border(None)
            return

        self._qr_last_payload = cleaned
        self._qr_last_scan_time = now

        self.student_id_var.set(student_code)
        self.student_name_var.set(name_value or "")

        display_name = name_value or student_code
        descriptor = f"{display_name} | {student_code}" if name_value else student_code
        self._set_qr_status(
            f"Last scanned: {descriptor}",
            tone="success",
        )
        if self._qr_auto_record_var.get():
            self._set_manual_status("Auto-record enabled. Logging attendance automatically.")
        else:
            self._set_manual_status("QR scan ready. Press Record to log attendance.")
        self._set_qr_preview_border(self._qr_scan_border_color)
        self._schedule_qr_border_reset(self._qr_scan_border_duration_ms)
        self._attempt_auto_record(cleaned)

    def _handle_qr_frame(self, frame: Any) -> None:
        if not self.winfo_exists():
            return
        if self._qr_preview_label is None:
            return
        if self._qr_preview_busy:
            return

        self._qr_preview_busy = True
        try:
            if frame is None:
                return

            try:
                import cv2  # type: ignore[import-not-found]
            except ImportError:
                return

            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_image = Image.fromarray(rgb_frame)
            resample_source = getattr(Image, "Resampling", Image)
            resample_filter = getattr(resample_source, "LANCZOS", getattr(resample_source, "BICUBIC", 2))
            square_image = ImageOps.fit(
                pil_image,
                self._qr_preview_size,
                method=resample_filter,
                centering=(0.5, 0.5),
            )
            self._qr_preview_image = ctk.CTkImage(
                light_image=square_image,
                dark_image=square_image,
                size=self._qr_preview_size,
            )
            self._qr_preview_label.configure(image=self._qr_preview_image, text="")
        except Exception:
            pass
        finally:
            self._qr_preview_busy = False

    def _handle_qr_error(self, message: str) -> None:
        self._set_qr_status(message, tone="warning")
        self._configure_qr_control(running=False)
        if self._qr_preview_label is not None:
            self._qr_preview_label.configure(image=self._qr_preview_placeholder, text="Camera preview inactive")
        self._qr_preview_image = None
        self._qr_preview_busy = False
        self._cancel_qr_border_reset()
        self._set_qr_preview_border(None)

    # ------------------------------------------------------------------
    # Recent session list helpers
    # ------------------------------------------------------------------
    def _refresh_recent_attendance(self) -> None:
        if not hasattr(self, "_recent_list"):
            return

        for widget in self._recent_list.winfo_children():
            widget.destroy()

        if not self._active_session_id:
            ctk.CTkLabel(self._recent_list, text="No attendance yet.", text_color=VS_TEXT_MUTED).pack(
                anchor="w", padx=12, pady=6
            )
            return

        records = self._service.recent_attendance_for_session(self._active_session_id, limit=8)
        if not records:
            ctk.CTkLabel(
                self._recent_list,
                text="No attendance logged for this session yet.",
                text_color=VS_TEXT_MUTED,
            ).pack(anchor="w", padx=12, pady=6)
            return

        hide_ids = self._hide_student_id_var.get()
        name_font = ctk.CTkFont(size=18, weight="bold")
        id_font = ctk.CTkFont(size=15)
        timestamp_font = ctk.CTkFont(size=15)

        for record in records:
            name_value = (record.get("student_name") or "").strip()
            display_name = name_value if name_value else record["student_id"]
            timestamp_text = ""
            if record.get("recorded_at"):
                try:
                    timestamp_text = format_relative_time(record["recorded_at"])
                except ValueError:
                    timestamp_text = ""

            card = ctk.CTkFrame(self._recent_list, corner_radius=10, fg_color=VS_CARD)
            card.pack(fill="x", padx=12, pady=6)
            card.grid_columnconfigure(0, weight=1)
            card.grid_columnconfigure(1, weight=0)

            info_frame = ctk.CTkFrame(card, fg_color="transparent")
            info_frame.grid(row=0, column=0, sticky="nsew", padx=12, pady=10)
            info_frame.grid_columnconfigure(0, weight=1)
            info_frame.grid_columnconfigure(1, weight=0)

            name_label = ctk.CTkLabel(info_frame, text=display_name, font=name_font, justify="left", text_color=VS_TEXT)
            name_label.grid(row=0, column=0, sticky="w")

            id_label = None
            if not hide_ids:
                id_label = ctk.CTkLabel(
                    info_frame,
                    text=record["student_id"],
                    font=id_font,
                    text_color=VS_TEXT_MUTED,
                    justify="left",
                )
                id_label.grid(row=0, column=1, sticky="e", padx=(12, 0))

            timestamp_label = None
            if timestamp_text:
                timestamp_label = ctk.CTkLabel(
                    card,
                    text=timestamp_text,
                    text_color=VS_TEXT_MUTED,
                    font=timestamp_font,
                )
                timestamp_label.grid(row=0, column=1, sticky="ne", padx=(4, 12), pady=10)

            def _update_layout(
                event,
                name_lbl=name_label,
                id_lbl=id_label,
                ts_lbl=timestamp_label,
                info=info_frame,
            ) -> None:
                available_width = event.width
                padding = 180 if ts_lbl else 80
                wrap_length = int(max(float(available_width - padding), 160))
                name_lbl.configure(wraplength=wrap_length)

                if id_lbl is None:
                    return

                threshold = 420 if ts_lbl else 340
                if available_width >= threshold:
                    id_lbl.grid_configure(row=0, column=1, sticky="e", padx=(12, 0), pady=0, columnspan=1)
                    name_lbl.grid_configure(row=0, column=0, columnspan=1)
                    id_lbl.configure(wraplength=int(max(wrap_length / 2, 120.0)))
                else:
                    id_lbl.grid_configure(row=1, column=0, columnspan=2, sticky="w", padx=(0, 0), pady=(6, 0))
                    name_lbl.grid_configure(row=0, column=0, columnspan=2)
                    id_lbl.configure(wraplength=wrap_length)

            card.bind("<Configure>", _update_layout)

    def _resolve_handler_name(
        self,
        handler: Callable[[ChromeRemoteController], BonusAutomationResult],
    ) -> str:
        name = getattr(handler, "__qualname__", None) or getattr(handler, "__name__", None)
        if name:
            return name
        return handler.__class__.__name__

    def _load_icon_image(
        self,
        filename: str,
        size: tuple[int, int],
    ) -> tuple[Image.Image | None, ctk.CTkImage | None]:
        try:
            base_path = Path(__file__).resolve()
            parents = base_path.parents
            candidate_roots = []
            if len(parents) > 3:
                candidate_roots.append(parents[3] / "assets")
            if len(parents) > 2:
                candidate_roots.append(parents[2] / "assets")
            if len(parents) > 1:
                candidate_roots.append(parents[1] / "assets")

            assets_root = next((path for path in candidate_roots if path.exists()), None)
            if assets_root is None:
                return None, None

            image_path = assets_root / filename
            if not image_path.exists():
                return None, None
            with Image.open(image_path) as img:
                pil_image = img.copy()
        except Exception:
            return None, None

        tk_image = ctk.CTkImage(light_image=pil_image, dark_image=pil_image, size=size)
        return pil_image, tk_image

    def _update_bonus_student_card(self, payload: Mapping[str, object] | None) -> None:
        card = self._bonus_student_card
        if card is None:
            return

        if not payload:
            self._bonus_student_name_display.set("")
            self._bonus_student_task_display.set("")
            self._bonus_student_time_display.set("")
            self._bonus_student_grade_display.set("")
            self._bonus_student_file_display.set("")
            if self._bonus_student_grade_label is not None:
                self._bonus_student_grade_label.grid_remove()
            if self._bonus_student_file_chip is not None:
                self._bonus_student_file_chip.grid_remove()

            card.grid_remove()
            return

        def _clean(value: object | None) -> str:
            if value is None:
                return ""
            text = str(value).strip()
            return text

        student_name = _clean(payload.get("student_name"))
        task_name = _clean(payload.get("task_name"))
        submission_time = _clean(payload.get("submission_time"))
        grade_info = _clean(payload.get("grade_info"))
        file_name = _clean(payload.get("file_name"))

        self._bonus_student_name_display.set(student_name or "Student details")

        if task_name and self._bonus_student_task_label is not None:
            display_task = task_name if task_name.startswith("📘") else f"📘 {task_name}"
            self._bonus_student_task_display.set(display_task)
            self._bonus_student_task_label.grid()
        else:
            self._bonus_student_task_display.set("")
            if self._bonus_student_task_label is not None:
                self._bonus_student_task_label.grid_remove()

        if submission_time and self._bonus_student_time_label is not None:
            prefix = "Submitted " if not submission_time.lower().startswith("submitted") else ""
            timeline = f"{prefix}{submission_time}"
            self._bonus_student_time_display.set(timeline if timeline.startswith("⏱") else f"⏱ {timeline}")
            self._bonus_student_time_label.grid()
        else:
            self._bonus_student_time_display.set("")
            if self._bonus_student_time_label is not None:
                self._bonus_student_time_label.grid_remove()

        if grade_info and self._bonus_student_grade_label is not None:
            self._bonus_student_grade_display.set(grade_info)
            self._bonus_student_grade_label.grid()
        else:
            self._bonus_student_grade_display.set("")
            if self._bonus_student_grade_label is not None:
                self._bonus_student_grade_label.grid_remove()

        if file_name and self._bonus_student_file_chip is not None:
            display_file = file_name if file_name.startswith("📎") else f"📎 {file_name}"
            self._bonus_student_file_display.set(display_file)
            self._bonus_student_file_chip.grid()
        else:
            self._bonus_student_file_display.set("")
            if self._bonus_student_file_chip is not None:
                self._bonus_student_file_chip.grid_remove()

        card.grid()

    def _is_chrome_session_active(self) -> bool:
        controller = self._chrome_controller
        if controller is None:
            return False
        try:
            return controller.is_browser_open()
        except Exception:  # pragma: no cover - defensive guard
            return False

    def _update_chrome_ui_state(self, *, chrome_active: bool | None = None) -> None:
        controller_available = self._chrome_controller is not None
        if chrome_active is None:
            chrome_active = controller_available and self._is_chrome_session_active()
        else:
            chrome_active = bool(chrome_active) and controller_available

        button = self._bonus_open_chrome_button
        if button is not None:
            if not controller_available:
                button.configure(state="disabled")
            else:
                desired_state = "disabled" if chrome_active else "normal"
                button.configure(state=desired_state)

        get_button = self._bonus_get_student_button
        if get_button is not None:
            if chrome_active and not self._bonus_fetch_in_progress:
                get_button.configure(state="normal")
            else:
                get_button.configure(state="disabled")

        if chrome_active:
            if self._bonus_instruction_var.get() != self._bonus_instruction_ready:
                self._bonus_instruction_var.set(self._bonus_instruction_ready)
            if self._bonus_output_var.get() in {
                self._chrome_inactive_message,
                self._bonus_default_output_message,
            }:
                self._bonus_output_var.set(self._chrome_ready_message)
        else:
            if self._bonus_instruction_var.get() != self._bonus_instruction_launch:
                self._bonus_instruction_var.set(self._bonus_instruction_launch)
            if self._bonus_output_var.get() != self._chrome_inactive_message:
                self._bonus_output_var.set(self._chrome_inactive_message)

    def _probe_chrome_state_async(self) -> None:
        if self._chrome_state_probe_inflight:
            return

        if not self._chrome_controller:
            self._update_chrome_ui_state(chrome_active=False)
            return

        self._chrome_state_probe_inflight = True

        def _worker() -> None:
            chrome_active = False
            controller = self._chrome_controller
            if controller is not None:
                try:
                    chrome_active = controller.is_browser_open()
                except Exception:
                    chrome_active = False

            def _finalize() -> None:
                self._chrome_state_probe_inflight = False
                if not self.winfo_exists():
                    return
                self._update_chrome_ui_state(chrome_active=chrome_active)

            try:
                self.after(0, _finalize)
            except Exception:
                self._chrome_state_probe_inflight = False

        threading.Thread(target=_worker, daemon=True).start()

    def _chrome_state_poll(self) -> None:
        self._chrome_state_poll_job = None
        if not self.winfo_exists():
            return
        self._probe_chrome_state_async()
        self._schedule_chrome_state_poll()

    def _schedule_chrome_state_poll(self, delay: int = 3000) -> None:
        if self._chrome_state_poll_job is not None:
            return
        if not self.winfo_exists():
            return
        self._chrome_state_poll_job = self.after(delay, self._chrome_state_poll)

    def _format_bonus_student_details(self, payload: Mapping[str, object]) -> str:
        field_labels = [
            ("student_name", "Student"),
            ("task_name", "Task"),
            ("submission_time", "Submitted"),
            ("grade_info", "Grade"),
            ("file_name", "File"),
        ]

        lines: list[str] = []
        for key, label in field_labels:
            value = payload.get(key)
            if value is None:
                continue

            text = str(value).strip()
            if text:
                lines.append(f"{label}: {text}")

        return "\n".join(lines)

    def destroy(self) -> None:  # pragma: no cover - lifecycle hook
        try:
            self._qr_scanner.stop()
        except Exception:
            pass
        if self._chrome_state_poll_job is not None:
            try:
                self.after_cancel(self._chrome_state_poll_job)
            except Exception:
                pass
            self._chrome_state_poll_job = None
        super().destroy()


class TemplateDialog(ctk.CTkToplevel):
    def __init__(self, master: TakeAttendanceView, service: AttendanceService) -> None:
        super().__init__(master)
        self.title("Create session")
        self.resizable(False, False)
        self.configure(fg_color=VS_BG)
        self.transient(master)
        self.grab_set()
        self.geometry("640x560")
        self.minsize(640, 560)
        self._service = service
        self._parent = master

        self.campus_var = StringVar(value=CAMPUS_OPTIONS[0])
        weekday_labels = [label for label, _ in WEEKDAY_OPTIONS]
        self.weekday_var = StringVar(value=weekday_labels[0])
        self.room_var = StringVar()
        self.start_var = StringVar()
        self.end_var = StringVar()

        self._status_var = StringVar(value="")

        self._build_form()
        self.after(10, self._center_on_parent)

    def _build_form(self) -> None:
        container = ctk.CTkFrame(
            self,
            corner_radius=20,
            fg_color=VS_SURFACE,
            border_width=1,
            border_color=VS_DIVIDER,
        )
        container.pack(fill="both", expand=True, padx=28, pady=28)
        container.grid_columnconfigure(0, weight=1)

        title_font = ctk.CTkFont(size=24, weight="bold")
        label_font = ctk.CTkFont(size=16, weight="bold")
        body_font = ctk.CTkFont(size=16)

        header = ctk.CTkFrame(container, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=24, pady=(24, 12))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="Create session",
            font=title_font,
            text_color=VS_TEXT,
        ).grid(row=0, column=0, sticky="w")

        form = ctk.CTkFrame(container, fg_color=VS_SURFACE_ALT, corner_radius=16)
        form.grid(row=1, column=0, padx=24, pady=(0, 20), sticky="ew")
        form.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkLabel(form, text="Campus", font=label_font, text_color=VS_TEXT).grid(
            row=0, column=0, padx=20, pady=(24, 6), sticky="w"
        )
        ctk.CTkLabel(form, text="Weekday", font=label_font, text_color=VS_TEXT).grid(
            row=0, column=1, padx=20, pady=(24, 6), sticky="w"
        )

        ctk.CTkOptionMenu(
            form,
            values=list(CAMPUS_OPTIONS),
            variable=self.campus_var,
            fg_color=VS_BG,
            button_color=VS_ACCENT,
            button_hover_color=VS_ACCENT_HOVER,
            text_color=VS_TEXT,
            font=body_font,
            height=44,
        ).grid(row=1, column=0, padx=20, pady=(0, 20), sticky="ew")

        weekday_labels = [label for label, _ in WEEKDAY_OPTIONS]
        ctk.CTkOptionMenu(
            form,
            values=weekday_labels,
            variable=self.weekday_var,
            fg_color=VS_BG,
            button_color=VS_ACCENT,
            button_hover_color=VS_ACCENT_HOVER,
            text_color=VS_TEXT,
            font=body_font,
            height=44,
        ).grid(row=1, column=1, padx=20, pady=(0, 20), sticky="ew")

        ctk.CTkLabel(form, text="Room number", font=label_font, text_color=VS_TEXT).grid(
            row=2, column=0, columnspan=2, padx=20, pady=(0, 6), sticky="w"
        )
        ctk.CTkEntry(
            form,
            textvariable=self.room_var,
            fg_color=VS_BG,
            border_color=VS_BORDER,
            text_color=VS_TEXT,
            placeholder_text="Room 3306",
            placeholder_text_color=VS_TEXT_MUTED,
            font=body_font,
            height=44,
        ).grid(row=3, column=0, columnspan=2, padx=20, pady=(0, 20), sticky="ew")

        ctk.CTkLabel(form, text="Start (hh)", font=label_font, text_color=VS_TEXT).grid(
            row=4, column=0, padx=20, pady=(0, 6), sticky="w"
        )
        ctk.CTkLabel(form, text="End (hh)", font=label_font, text_color=VS_TEXT).grid(
            row=4, column=1, padx=20, pady=(0, 6), sticky="w"
        )

        ctk.CTkEntry(
            form,
            textvariable=self.start_var,
            placeholder_text="12",
            fg_color=VS_BG,
            border_color=VS_BORDER,
            text_color=VS_TEXT,
            placeholder_text_color=VS_TEXT_MUTED,
            font=body_font,
            height=44,
        ).grid(row=5, column=0, padx=20, pady=(0, 20), sticky="ew")

        ctk.CTkEntry(
            form,
            textvariable=self.end_var,
            placeholder_text="14",
            fg_color=VS_BG,
            border_color=VS_BORDER,
            text_color=VS_TEXT,
            placeholder_text_color=VS_TEXT_MUTED,
            font=body_font,
            height=44,
        ).grid(row=5, column=1, padx=20, pady=(0, 20), sticky="ew")

        ctk.CTkLabel(
            form,
            text="Create a class/session for your weekly attendance sessions.",
            font=body_font,
            text_color=VS_TEXT_MUTED,
            justify="left",
            wraplength=460,
        ).grid(row=6, column=0, columnspan=2, padx=20, pady=(0, 24), sticky="w")

        self._status_label = ctk.CTkLabel(
            container,
            textvariable=self._status_var,
            font=body_font,
            text_color=VS_WARNING,
        )
        self._status_label.grid(row=2, column=0, padx=24, pady=(0, 8), sticky="w")

        button_row = ctk.CTkFrame(container, fg_color="transparent")
        button_row.grid(row=3, column=0, padx=24, pady=(0, 24), sticky="ew")
        button_row.grid_columnconfigure(0, weight=1)
        button_row.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(
            button_row,
            text="Cancel",
            height=44,
            font=body_font,
            fg_color=VS_SURFACE_ALT,
            hover_color=VS_DIVIDER,
            text_color=VS_TEXT,
            command=self.destroy,
        ).grid(row=0, column=0, padx=(0, 10), sticky="ew")

        ctk.CTkButton(
            button_row,
            text="Create session",
            height=44,
            font=ctk.CTkFont(size=17, weight="bold"),
            command=self._handle_create,
            fg_color=VS_ACCENT,
            hover_color=VS_ACCENT_HOVER,
            text_color=VS_TEXT,
        ).grid(row=0, column=1, padx=(10, 0), sticky="ew")

        container.grid_rowconfigure(4, weight=1)

    def _handle_create(self) -> None:
        campus = self.campus_var.get().strip()
        weekday_label = self.weekday_var.get()
        room = self.room_var.get().strip()
        start_text = self.start_var.get().strip()
        end_text = self.end_var.get().strip()

        if not all([campus, weekday_label, room, start_text, end_text]):
            self._status_var.set("All fields are required.")
            return

        try:
            start_hour, end_hour = parse_hour_range(start_text, end_text)
        except InvalidHourRange as exc:
            self._status_var.set(str(exc))
            return

        weekday_map = {label: idx for label, idx in WEEKDAY_OPTIONS}
        weekday_index = weekday_map.get(weekday_label)
        if weekday_index is None:
            self._status_var.set("Invalid weekday selection.")
            return

        template_id = self._service.create_session_template(
            campus_name=campus,
            weekday_index=weekday_index,
            room_code=room,
            start_hour=start_hour,
            end_hour=end_hour,
        )

        if template_id <= 0:
            self._status_var.set("Template already exists.")
            return

        self._parent._load_templates()
        self.destroy()

    def _center_on_parent(self) -> None:
        try:
            parent = self._parent.winfo_toplevel()
        except Exception:
            parent = None

        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()

        if parent is not None and parent.winfo_exists():
            parent.update_idletasks()
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            pwidth = parent.winfo_width()
            pheight = parent.winfo_height()
            x = px + max((pwidth - width) // 2, 0)
            y = py + max((pheight - height) // 2, 0)
        else:
            screen_width = self.winfo_screenwidth()
            screen_height = self.winfo_screenheight()
            x = max((screen_width - width) // 2, 0)
            y = max((screen_height - height) // 2, 0)

        self.geometry(f"{width}x{height}+{x}+{y}")
