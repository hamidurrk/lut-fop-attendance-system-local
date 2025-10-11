from __future__ import annotations

from attendance_app.ui.components.collapsible_nav import NavigationItem


NAV_ITEMS: tuple[NavigationItem, ...] = (
    NavigationItem(
        key="take_attendance",
        label="Take attendance",
        icon_text="TA",
        icon_filename="attendance.png",
    ),
    NavigationItem(
        key="history",
        label="Manage records",
        icon_text="MR",
        icon_filename="manage.png",
    ),
    NavigationItem(
        key="auto_grader",
        label="Auto-grader",
        icon_text="AG",
        icon_filename="autograder.png",
    ),
    NavigationItem(
        key="settings",
        label="Settings",
        icon_text="ST",
        icon_filename="settings.png",
    ),
)
