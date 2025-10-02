from __future__ import annotations

import tkinter.messagebox as messagebox
from tkinter import BooleanVar, IntVar, StringVar
from typing import Callable

import customtkinter as ctk

from attendance_app.models import AttendanceSession, SessionTemplate, Student
from attendance_app.services import AttendanceService, DuplicateAttendanceError, DuplicateSessionError
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

CAMPUS_OPTIONS: tuple[str, ...] = ("Lappeenranta", "Lahti")


class TakeAttendanceView(ctk.CTkFrame):
    WEEK_OPTIONS = tuple(str(week) for week in range(1, 15))

    def __init__(
        self,
        master,
        attendance_service: AttendanceService,
        *,
        on_session_started: Callable[[], None] | None = None,
        on_session_ended: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(master, fg_color=VS_BG)
        self._service = attendance_service
        self._active_session_id: int | None = None
        self._on_session_started = on_session_started
        self._on_session_ended = on_session_ended

        self._status_var = StringVar(value="Choose a session template to get started.")
        self._session_info_var = StringVar(value="")
        self._qr_status_var = StringVar(value="Scanner idle")
        self._manual_status_var = StringVar(value="")

        self.student_name_var = StringVar()
        self.student_id_var = StringVar()
        self._hide_student_id_var = BooleanVar(value=False)

        self.selected_template_label = StringVar(value="No session templates")
        self.selected_template_id = IntVar(value=0)
        self.chapter_var = StringVar()
        self.week_var = StringVar(value=self.WEEK_OPTIONS[0])

        self._templates: list[SessionTemplate] = []

        self._build_widgets()
        self._load_templates()
        self.refresh_recent_sessions()

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

    # ------------------------------------------------------------------
    # Layout construction
    # ------------------------------------------------------------------
    def _build_widgets(self) -> None:
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        container = ctk.CTkFrame(self, corner_radius=14, fg_color=VS_SURFACE)
        container.grid(row=0, column=0, padx=24, pady=24, sticky="nsew")
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)

        self._session_form_frame = ctk.CTkFrame(container, corner_radius=12, fg_color=VS_SURFACE_ALT)
        self._session_form_frame.grid(row=0, column=0, padx=24, pady=24, sticky="nsew")
        self._session_form_frame.grid_columnconfigure(0, weight=1)
        self._session_form_frame.grid_columnconfigure(1, weight=1)
        self._build_session_form(self._session_form_frame)

        self._attendance_container = ctk.CTkFrame(container, fg_color=VS_SURFACE)
        self._attendance_container.grid(row=0, column=0, padx=24, pady=24, sticky="nsew")
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

        self._left_stack = ctk.CTkFrame(self._attendance_container, fg_color=VS_SURFACE)
        self._left_stack.grid(row=1, column=0, sticky="nsew", padx=(0, 12))
        self._left_stack.grid_columnconfigure(0, weight=1)
        self._left_stack.grid_rowconfigure(0, weight=1)
        self._left_stack.grid_rowconfigure(1, weight=2)

        self._manual_frame = ctk.CTkFrame(self._left_stack, corner_radius=12, fg_color=VS_SURFACE_ALT)
        self._manual_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 12))
        self._build_manual_panel(self._manual_frame)

        self._recent_frame = ctk.CTkFrame(self._left_stack, corner_radius=12, fg_color=VS_SURFACE_ALT)
        self._recent_frame.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        self._build_recent_panel(self._recent_frame)

        self._qr_frame = ctk.CTkFrame(self._attendance_container, corner_radius=12, fg_color=VS_SURFACE_ALT)
        self._qr_frame.grid(row=1, column=1, sticky="nsew", padx=(12, 0))
        self._build_qr_panel(self._qr_frame)

    def _build_session_form(self, frame: ctk.CTkFrame) -> None:
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_columnconfigure(1, weight=1)

        header_row = ctk.CTkFrame(frame, fg_color=VS_SURFACE_ALT)
        header_row.grid(row=0, column=0, columnspan=2, padx=24, pady=(24, 12), sticky="ew")
        header_row.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header_row,
            text="Select session",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=VS_TEXT,
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkButton(
            header_row,
            text="Create new session",
            width=180,
            fg_color=VS_ACCENT,
            hover_color=VS_ACCENT_HOVER,
            text_color=VS_TEXT,
            command=self._open_template_dialog,
        ).grid(row=0, column=1, sticky="e")

        self.template_menu = ctk.CTkOptionMenu(
            frame,
            values=[self.selected_template_label.get()],
            variable=self.selected_template_label,
            command=self._handle_template_select,
            fg_color=VS_BG,
            button_color=VS_ACCENT,
            button_hover_color=VS_ACCENT_HOVER,
            text_color=VS_TEXT,
        )
        self.template_menu.grid(row=1, column=0, columnspan=2, padx=24, pady=(0, 16), sticky="ew")

        info_card = ctk.CTkFrame(frame, corner_radius=10, fg_color=VS_CARD)
        info_card.grid(row=2, column=0, columnspan=2, padx=24, pady=(0, 20), sticky="ew")
        info_card.grid_columnconfigure(0, weight=1)
        self._template_info_label = ctk.CTkLabel(
            info_card,
            text="No template selected",
            justify="left",
            text_color=VS_TEXT_MUTED,
        )
        self._template_info_label.grid(row=0, column=0, padx=16, pady=16, sticky="w")

        label_font = ctk.CTkFont(size=16)

        ctk.CTkLabel(frame, text="Chapter code", text_color=VS_TEXT, font=label_font).grid(
            row=3, column=0, padx=24, pady=6, sticky="w"
        )
        chapter_entry = ctk.CTkEntry(
            frame,
            textvariable=self.chapter_var,
            fg_color=VS_BG,
            border_color=VS_BORDER,
            text_color=VS_TEXT,
            placeholder_text_color=VS_TEXT_MUTED,
        )
        chapter_entry.grid(row=3, column=1, padx=24, pady=6, sticky="ew")

        ctk.CTkLabel(frame, text="Week", text_color=VS_TEXT, font=label_font).grid(
            row=4, column=0, padx=24, pady=6, sticky="w"
        )
        week_menu = ctk.CTkOptionMenu(
            frame,
            values=self.WEEK_OPTIONS,
            variable=self.week_var,
            fg_color=VS_BG,
            button_color=VS_ACCENT,
            button_hover_color=VS_ACCENT_HOVER,
            text_color=VS_TEXT,
        )
        week_menu.grid(row=4, column=1, padx=24, pady=6, sticky="ew")

        self._status_label = ctk.CTkLabel(frame, textvariable=self._status_var, text_color=VS_TEXT_MUTED)
        self._status_label.grid(row=5, column=0, columnspan=2, padx=24, pady=(12, 8), sticky="w")
        self._update_status_message(self._status_var.get())

        start_btn = ctk.CTkButton(
            frame,
            text="Start session",
            command=self._handle_start_session,
            fg_color=VS_ACCENT,
            hover_color=VS_ACCENT_HOVER,
            text_color=VS_TEXT,
        )
        start_btn.grid(row=6, column=0, columnspan=2, padx=24, pady=(4, 24), sticky="ew")

    def _build_recent_panel(self, frame: ctk.CTkFrame) -> None:
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(2, weight=1)

        header_font = ctk.CTkFont(size=20, weight="bold")
        label_font = ctk.CTkFont(size=18)

        ctk.CTkLabel(frame, text="Recently logged students", font=header_font, text_color=VS_TEXT).grid(
            row=0, column=0, padx=20, pady=(20, 8), sticky="w"
        )

        toggle_row = ctk.CTkFrame(frame, fg_color=VS_SURFACE_ALT)
        toggle_row.grid(row=1, column=0, padx=20, pady=(0, 8), sticky="ew")
        toggle_row.grid_columnconfigure(0, weight=1)

        ctk.CTkSwitch(
            toggle_row,
            text="Hide student ID",
            variable=self._hide_student_id_var,
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
            font=ctk.CTkFont(size=18, weight="bold"),
            fg_color=VS_ACCENT,
            hover_color=VS_ACCENT_HOVER,
            text_color=VS_TEXT,
        ).grid(row=0, column=1, sticky="e")

    def _build_qr_panel(self, frame: ctk.CTkFrame) -> None:
        frame.grid_rowconfigure(1, weight=1)
        header_font = ctk.CTkFont(size=20, weight="bold")
        body_font = ctk.CTkFont(size=15)

        ctk.CTkLabel(frame, text="QR scanner", font=header_font, text_color=VS_TEXT).grid(
            row=0, column=0, padx=20, pady=(20, 8), sticky="w"
        )
        ctk.CTkLabel(
            frame,
            text=(
                "QR scanner placeholder\n"
                "Integrate camera feed via OpenCV\n"
                "to enable automatic detection."
            ),
            justify="left",
            font=body_font,
            text_color=VS_TEXT_MUTED,
        ).grid(row=1, column=0, padx=20, pady=16, sticky="nsew")
        ctk.CTkLabel(frame, textvariable=self._qr_status_var, text_color=VS_TEXT_MUTED, font=body_font).grid(
            row=2, column=0, padx=20, pady=(4, 20), sticky="w"
        )

    # ------------------------------------------------------------------
    # Session template management
    # ------------------------------------------------------------------
    def _load_templates(self) -> None:
        self._templates = self._service.list_session_templates()
        if not self._templates:
            self.template_menu.configure(values=["No session templates"], state="disabled")
            self.selected_template_label.set("No session templates")
            self._template_info_label.configure(text="Create a session template to begin.")
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
                        f"{template.campus_name}\n"
                        f"{template.weekday_label()} · {template.start_hour:02d}-{template.end_hour:02d}\n"
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
            self._update_status_message("Select a session template first.", tone="warning")
            return

        if not chapter or not week_value:
            self._update_status_message("Chapter and week are required.", tone="warning")
            return

        template = self._service.get_session_template(template_id)
        if not template:
            self._update_status_message("Template not found. Create a new one.", tone="warning")
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
        self.refresh_recent_sessions()
        if self._on_session_started:
            self._on_session_started()

    def _handle_end_session(self) -> None:
        self._active_session_id = None
        self._session_info_var.set("")
        self.student_name_var.set("")
        self.student_id_var.set("")
        self._qr_status_var.set("Scanner idle")
        self._set_manual_status("")
        if hasattr(self, "_active_header"):
            self._active_header.configure(text=self._default_header_text)
        if hasattr(self, "_end_session_button"):
            self._end_session_button.configure(state="disabled")
        self._show_session_form()
        if self._on_session_ended:
            self._on_session_ended()

    def _activate_session(self, session: AttendanceSession, session_id: int) -> None:
        self._active_session_id = session_id
        self._session_info_var.set(
            (
                f"Session {session_id} · {session.chapter_code} "
                f"Week {session.week_number}\n"
                f"{session.campus_name} · {session.room_code}"
            )
        )
        self._update_status_message(f"Session {session_id} started. Ready for attendance.", tone="success")
        if hasattr(self, "_active_header"):
            self._active_header.configure(
                text=(
                    f"{session.chapter_code} · Week {session.week_number}"
                    f" — {session.campus_name} · {session.room_code}"
                )
            )
        if hasattr(self, "_end_session_button"):
            self._end_session_button.configure(state="normal")
        self._show_attendance_ui()

    def _show_session_form(self) -> None:
        self._attendance_container.grid_remove()
        self._session_form_frame.grid()
        self._update_status_message("Choose a session template to get started.")
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
    def _handle_manual_record(self) -> None:
        self._set_manual_status("")

        if not self._active_session_id:
            self._set_manual_status("Start a session before recording attendance.", tone="warning")
            return

        student_code = self.student_id_var.get().strip()
        if not student_code:
            self._set_manual_status("Student ID is required.", tone="warning")
            return

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
            self._service.record_attendance(self._active_session_id, student, source="manual")
        except DuplicateAttendanceError:
            self._set_manual_status(f"{student_code} is already logged for this session.", tone="warning")
            return
        except Exception as exc:  # pragma: no cover - guard unexpected issues
            self._set_manual_status(f"Failed to record attendance: {exc}", tone="warning")
            return

        self.student_id_var.set("")
        self.student_name_var.set("")
        self.refresh_recent_sessions()
        self._set_manual_status(f"Recorded {student_code}.", tone="success")

    # ------------------------------------------------------------------
    # Recent session list helpers
    # ------------------------------------------------------------------
    def refresh_recent_sessions(self) -> None:
        if not hasattr(self, "_recent_list"):
            return

        for widget in self._recent_list.winfo_children():
            widget.destroy()

        records = self._service.recent_attendance_records(limit=8)
        if not records:
            ctk.CTkLabel(self._recent_list, text="No attendance yet.", text_color=VS_TEXT_MUTED).pack(
                anchor="w", padx=12, pady=6
            )
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


class TemplateDialog(ctk.CTkToplevel):
    def __init__(self, master: TakeAttendanceView, service: AttendanceService) -> None:
        super().__init__(master)
        self.title("Create session template")
        self.geometry("420x420")
        self.resizable(False, False)
        self.configure(fg_color=VS_BG)
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

    def _build_form(self) -> None:
        frame = ctk.CTkFrame(self, fg_color=VS_SURFACE)
        frame.pack(fill="both", expand=True, padx=20, pady=20)
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_columnconfigure(1, weight=1)

        label_font = ctk.CTkFont(size=16)

        ctk.CTkLabel(frame, text="Campus", text_color=VS_TEXT, font=label_font).grid(
            row=0, column=0, padx=12, pady=8, sticky="w"
        )
        ctk.CTkOptionMenu(
            frame,
            values=list(CAMPUS_OPTIONS),
            variable=self.campus_var,
            fg_color=VS_BG,
            button_color=VS_ACCENT,
            button_hover_color=VS_ACCENT_HOVER,
            text_color=VS_TEXT,
        ).grid(
            row=0, column=1, padx=12, pady=8, sticky="ew"
        )

        weekday_labels = [label for label, _ in WEEKDAY_OPTIONS]
        ctk.CTkLabel(frame, text="Weekday", text_color=VS_TEXT, font=label_font).grid(
            row=1, column=0, padx=12, pady=8, sticky="w"
        )
        ctk.CTkOptionMenu(
            frame,
            values=weekday_labels,
            variable=self.weekday_var,
            fg_color=VS_BG,
            button_color=VS_ACCENT,
            button_hover_color=VS_ACCENT_HOVER,
            text_color=VS_TEXT,
        ).grid(
            row=1, column=1, padx=12, pady=8, sticky="ew"
        )

        ctk.CTkLabel(frame, text="Room number", text_color=VS_TEXT, font=label_font).grid(
            row=2, column=0, padx=12, pady=8, sticky="w"
        )
        ctk.CTkEntry(
            frame,
            textvariable=self.room_var,
            fg_color=VS_BG,
            border_color=VS_BORDER,
            text_color=VS_TEXT,
            placeholder_text_color=VS_TEXT_MUTED,
        ).grid(row=2, column=1, padx=12, pady=8, sticky="ew")

        ctk.CTkLabel(frame, text="Time from (hh)", text_color=VS_TEXT, font=label_font).grid(
            row=3, column=0, padx=12, pady=8, sticky="w"
        )
        ctk.CTkEntry(
            frame,
            textvariable=self.start_var,
            placeholder_text="12",
            fg_color=VS_BG,
            border_color=VS_BORDER,
            text_color=VS_TEXT,
            placeholder_text_color=VS_TEXT_MUTED,
        ).grid(
            row=3, column=1, padx=12, pady=8, sticky="ew"
        )

        ctk.CTkLabel(frame, text="Time to (hh)", text_color=VS_TEXT, font=label_font).grid(
            row=4, column=0, padx=12, pady=8, sticky="w"
        )
        ctk.CTkEntry(
            frame,
            textvariable=self.end_var,
            placeholder_text="14",
            fg_color=VS_BG,
            border_color=VS_BORDER,
            text_color=VS_TEXT,
            placeholder_text_color=VS_TEXT_MUTED,
        ).grid(
            row=4, column=1, padx=12, pady=8, sticky="ew"
        )

        ctk.CTkLabel(frame, textvariable=self._status_var, text_color=VS_TEXT_MUTED).grid(
            row=5, column=0, columnspan=2, padx=12, pady=(4, 12), sticky="w"
        )

        button_row = ctk.CTkFrame(frame, fg_color=VS_SURFACE)
        button_row.grid(row=6, column=0, columnspan=2, padx=12, pady=(0, 4), sticky="ew")
        button_row.grid_columnconfigure(0, weight=1)
        button_row.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(
            button_row,
            text="Cancel",
            fg_color=VS_SURFACE_ALT,
            hover_color=VS_DIVIDER,
            text_color=VS_TEXT,
            command=self.destroy,
        ).grid(row=0, column=0, padx=(0, 6), pady=4, sticky="ew")

        ctk.CTkButton(
            button_row,
            text="Create",
            command=self._handle_create,
            fg_color=VS_ACCENT,
            hover_color=VS_ACCENT_HOVER,
            text_color=VS_TEXT,
        ).grid(
            row=0, column=1, padx=(6, 0), pady=4, sticky="ew"
        )

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
