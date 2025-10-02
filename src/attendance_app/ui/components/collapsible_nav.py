from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

import customtkinter as ctk

from attendance_app.ui.theme import (
    VS_ACCENT,
    VS_ACCENT_HOVER,
    VS_BORDER,
    VS_SIDEBAR,
    VS_SURFACE_ALT,
    VS_TEXT,
    VS_TEXT_MUTED,
)


@dataclass(frozen=True)
class NavigationItem:
    key: str
    label: str
    icon_text: str | None = None


class CollapsibleNav(ctk.CTkFrame):
    def __init__(
        self,
        master,
        items: Iterable[NavigationItem],
        on_select: Callable[[str], None],
        *,
        width: int = 220,
    ) -> None:
        super().__init__(
            master,
            width=width,
            corner_radius=0,
            fg_color=VS_SIDEBAR,
            border_width=1,
            border_color=VS_BORDER,
        )
        self._items = list(items)
        self._on_select = on_select
        self._is_collapsed = False
        self._expanded_width = width
        self._collapsed_width = 72
        self._enabled = True

        self.grid_columnconfigure(0, weight=1)
        self.grid_propagate(False)
        self.configure(width=self._expanded_width)

        self.grid_rowconfigure(tuple(range(len(self._items) + 2)), weight=0)
        self.grid_rowconfigure(len(self._items) + 2, weight=1)

        toggle_font = ctk.CTkFont(size=20, weight="bold")
        self._toggle_button = ctk.CTkButton(
            self,
            text="☰",
            width=self._expanded_width - 24,
            height=36,
            command=self._toggle,
            corner_radius=6,
            fg_color=VS_SURFACE_ALT,
            hover_color=VS_ACCENT_HOVER,
            text_color=VS_TEXT,
            font=toggle_font,
            border_width=1,
            border_color=VS_BORDER,
        )
        self._toggle_button.grid(row=0, column=0, padx=8, pady=(12, 6), sticky="ew")

        self._buttons: dict[str, ctk.CTkButton] = {}
        button_font = ctk.CTkFont(size=16, weight="bold")
        for index, item in enumerate(self._items, start=1):
            button = ctk.CTkButton(
                self,
                text=item.label,
                width=self._expanded_width - 24,
                anchor="w",
                command=lambda k=item.key: self._handle_select(k),
                height=36,
                fg_color=VS_SIDEBAR,
                hover_color=VS_SURFACE_ALT,
                text_color=VS_TEXT,
                font=button_font,
                border_width=1,
                border_color=VS_BORDER,
            )
            button.grid(row=index, column=0, padx=12, pady=4, sticky="ew")
            self._buttons[item.key] = button

        self._selection_key: str | None = None

    def select(self, key: str) -> None:
        if key not in self._buttons:
            return
        if self._selection_key:
            self._buttons[self._selection_key].configure(fg_color=VS_SIDEBAR, text_color=VS_TEXT)
        self._buttons[key].configure(fg_color=VS_ACCENT, text_color=VS_TEXT)
        self._selection_key = key
        self._on_select(key)

    def _handle_select(self, key: str) -> None:
        self.select(key)

    def _toggle(self) -> None:
        if not self._enabled:
            return
        self._is_collapsed = not self._is_collapsed
        new_width = self._collapsed_width if self._is_collapsed else self._expanded_width
        self.configure(width=new_width)
        self._toggle_button.configure(
            text="☰" if not self._is_collapsed else "➤",
            width=new_width - 24,
        )
        for item in self._items:
            button = self._buttons[item.key]
            if self._is_collapsed:
                text = item.icon_text or item.label[:2].upper()
                button.configure(text=text, anchor="center", width=new_width - 24)
            else:
                button.configure(text=item.label, anchor="w", width=new_width - 24)

        self.update_idletasks()

    def collapse(self) -> None:
        if not self._is_collapsed:
            self._toggle()

    def expand(self) -> None:
        if self._is_collapsed:
            self._toggle()

    def set_navigation_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        state = "normal" if enabled else "disabled"
        toggle_color = VS_SURFACE_ALT if enabled else VS_SURFACE_ALT
        text_color = VS_TEXT if enabled else VS_TEXT_MUTED
        self._toggle_button.configure(state=state, fg_color=toggle_color, text_color=text_color)
        for key, button in self._buttons.items():
            button.configure(state=state)
            if not enabled:
                button.configure(text_color=VS_TEXT_MUTED)
            elif self._selection_key == key:
                button.configure(text_color=VS_TEXT)
            else:
                button.configure(text_color=VS_TEXT)
