from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

import customtkinter as ctk
from PIL import Image

from attendance_app.ui.theme import (
    VS_ACCENT,
    VS_ACCENT_HOVER,
    VS_BORDER,
    VS_SIDEBAR,
    VS_SURFACE_ALT,
    VS_TEXT,
    VS_TEXT_MUTED,
)
from attendance_app.ui.utils import load_icon_image

ICON_SIZE: tuple[int, int] = (32, 32)
BUTTON_HEIGHT = ICON_SIZE[1] + 18


@dataclass(frozen=True)
class NavigationItem:
    key: str
    label: str
    icon_text: str | None = None
    icon_filename: str | None = None


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
        self._collapsed_width = max(ICON_SIZE[0] + 44, 84)
        self._enabled = True
        self._button_icons: dict[str, tuple[Image.Image | None, ctk.CTkImage | None]] = {}

        self.grid_columnconfigure(0, weight=1)
        self.grid_propagate(False)
        self.configure(width=self._expanded_width)

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

        for item in self._items:
            if item.icon_filename:
                self._button_icons[item.key] = load_icon_image(item.icon_filename, ICON_SIZE)
            else:
                self._button_icons[item.key] = (None, None)

        self._buttons: dict[str, ctk.CTkButton] = {}
        button_font = ctk.CTkFont(size=16, weight="bold")

        top_items = [item for item in self._items if item.key != "settings"]
        bottom_items = [item for item in self._items if item.key == "settings"]

        row_index = 1
        for item in top_items:
            _, icon_image = self._button_icons.get(item.key, (None, None))
            button = ctk.CTkButton(
                self,
                text=item.label,
                width=self._expanded_width - 24,
                anchor="w",
                command=lambda k=item.key: self._handle_select(k),
                height=BUTTON_HEIGHT,
                fg_color=VS_SIDEBAR,
                hover_color=VS_SURFACE_ALT,
                text_color=VS_TEXT,
                font=button_font,
                border_width=1,
                border_color=VS_BORDER,
                image=icon_image,
                compound="left" if icon_image is not None else "center",
            )
            button.grid(row=row_index, column=0, padx=12, pady=4, sticky="ew")
            self._buttons[item.key] = button
            row_index += 1

        spacer_row = row_index
        self.grid_rowconfigure(spacer_row, weight=1)
        row_index += 1

        for item in bottom_items:
            _, icon_image = self._button_icons.get(item.key, (None, None))
            button = ctk.CTkButton(
                self,
                text=item.label,
                width=self._expanded_width - 24,
                anchor="w",
                command=lambda k=item.key: self._handle_select(k),
                height=BUTTON_HEIGHT,
                fg_color=VS_SIDEBAR,
                hover_color=VS_SURFACE_ALT,
                text_color=VS_TEXT,
                font=button_font,
                border_width=1,
                border_color=VS_BORDER,
                image=icon_image,
                compound="center" if icon_image is not None else "center",
            )
            button.grid(row=row_index, column=0, padx=12, pady=12, sticky="ew")
            self._buttons[item.key] = button
            row_index += 1

        if not bottom_items:
            self.grid_rowconfigure(spacer_row, weight=1)

        self._selection_key: str | None = None
        self._update_buttons_for_state(self._expanded_width)

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
        self._update_buttons_for_state(new_width)

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

    def refresh_layout(self):
        target_width = self._collapsed_width if self._is_collapsed else self._expanded_width
        self.configure(width=target_width)
        self._toggle_button.configure(
            text="☰" if not self._is_collapsed else "➤",
            width=target_width - 24,
        )
        self._update_buttons_for_state(target_width)

    def _update_buttons_for_state(self, current_width: int) -> None:
        target_width = current_width - 24
        for item in self._items:
            button = self._buttons[item.key]
            _, icon_image = self._button_icons.get(item.key, (None, None))
            if self._is_collapsed:
                if icon_image is not None:
                    button.configure(
                        text="",
                        image=icon_image,
                        compound="center",
                        anchor="center",
                        width=target_width,
                        border_spacing=0,
                    )
                else:
                    text = item.icon_text or item.label[:2].upper()
                    button.configure(
                        text=text,
                        image=None,
                        compound="center",
                        anchor="center",
                        width=target_width,
                        border_spacing=0,
                    )
            else:
                if icon_image is not None:
                    button.configure(
                        text=item.label,
                        image=icon_image,
                        compound="left",
                        anchor="w",
                        width=target_width,
                        border_spacing=6,
                    )
                else:
                    button.configure(
                        text=item.label,
                        image=None,
                        compound="center",
                        anchor="w",
                        width=target_width,
                        border_spacing=6,
                    )
