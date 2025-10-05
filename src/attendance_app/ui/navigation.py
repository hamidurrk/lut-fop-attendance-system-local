from __future__ import annotations

from attendance_app.ui.components.collapsible_nav import NavigationItem


NAV_ITEMS: tuple[NavigationItem, ...] = (
    NavigationItem(key="take_attendance", label="Take attendance", icon_text="TA"),
    NavigationItem(key="history", label="Manage records", icon_text="MR"),
    NavigationItem(key="auto_grader", label="Auto-grader", icon_text="AG"),
)
