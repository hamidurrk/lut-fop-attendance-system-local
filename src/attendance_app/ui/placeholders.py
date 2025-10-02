from __future__ import annotations

import customtkinter as ctk
from attendance_app.ui.theme import VS_BG, VS_TEXT, VS_TEXT_MUTED


class PlaceholderView(ctk.CTkFrame):
    def __init__(self, master, *, title: str, message: str = "") -> None:
        super().__init__(master, fg_color=VS_BG)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        label = ctk.CTkLabel(
            self,
            text=title,
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color=VS_TEXT,
        )
        label.grid(row=0, column=0, padx=12, pady=(80, 12))
        subtitle = ctk.CTkLabel(
            self,
            text=message or "Feature under construction.",
            text_color=VS_TEXT_MUTED,
        )
        subtitle.grid(row=1, column=0, padx=12, pady=6)
