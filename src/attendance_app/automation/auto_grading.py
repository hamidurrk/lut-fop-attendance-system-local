"""Auto-grading workflow placeholders.

Implement the Selenium automation routine in :func:`run_auto_grading` and the
Auto-grader view will call it sequentially for each student. Returning ``True``
marks the student as graded, while a falsy value leaves the record unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import sleep
from typing import Callable, Iterable, Protocol

from .chrome import ChromeRemoteController

_VALID_TONES = {"info", "success", "warning"}


@dataclass(slots=True)
class AutoGradingSessionContext:

    prompt_callback: Callable[[str], bool] | None = None
    assignment_id: str | None = None
    is_confirmed: bool | None = None

    def ensure_assignment_id(self, new_id: str) -> str:
        if self.assignment_id is None:
            self.assignment_id = new_id
        elif self.assignment_id != new_id:
            raise ValueError("Assignment context changed while auto-grading was running.")
        return self.assignment_id

    def ensure_confirmation(self, message: str) -> bool:
        if self.is_confirmed is None:
            if self.prompt_callback is None:
                raise RuntimeError("No prompt callback available to confirm automation question.")
            self.is_confirmed = bool(self.prompt_callback(message))
        return bool(self.is_confirmed)


@dataclass(slots=True)
class AutoGradingMessage:

    text: str
    tone: str = "info"

    def normalized_tone(self) -> str:
        tone = (self.tone or "info").lower()
        if tone not in _VALID_TONES:
            return "info"
        return tone


@dataclass(slots=True)
class AutoGradingResult:

    success: bool
    messages: tuple[AutoGradingMessage, ...] = ()
    should_stop: bool = False

    def __bool__(self) -> bool:  # pragma: no cover - boolean contract is critical
        return self.success

    @classmethod
    def success_result(
        cls,
        message: AutoGradingMessage | str | Iterable[AutoGradingMessage | str] | None = None,
        *,
        should_stop: bool = False,
        tone: str = "success",
    ) -> "AutoGradingResult":
        return cls(True, cls._coerce_messages(message, tone), should_stop)

    @classmethod
    def failure_result(
        cls,
        message: AutoGradingMessage | str | Iterable[AutoGradingMessage | str] | None = None,
        *,
        should_stop: bool = False,
        tone: str = "warning",
    ) -> "AutoGradingResult":
        return cls(False, cls._coerce_messages(message, tone), should_stop)

    @classmethod
    def info_result(
        cls,
        message: AutoGradingMessage | str | Iterable[AutoGradingMessage | str] | None,
        *,
        success: bool = True,
        should_stop: bool = False,
    ) -> "AutoGradingResult":
        return cls(success, cls._coerce_messages(message, "info"), should_stop)

    @staticmethod
    def ensure(value: "AutoGradingResult | bool | None") -> "AutoGradingResult":
        if isinstance(value, AutoGradingResult):
            return value
        return AutoGradingResult(bool(value), () if value else ())

    @staticmethod
    def _coerce_messages(
        messages: AutoGradingMessage | str | Iterable[AutoGradingMessage | str] | None,
        default_tone: str,
    ) -> tuple[AutoGradingMessage, ...]:
        if messages is None:
            return ()
        if isinstance(messages, AutoGradingMessage):
            return (AutoGradingMessage(messages.text, messages.tone),)
        if isinstance(messages, str):
            return (AutoGradingMessage(messages, default_tone),)

        normalized: list[AutoGradingMessage] = []
        for item in messages:
            if isinstance(item, AutoGradingMessage):
                normalized.append(AutoGradingMessage(item.text, item.tone))
            else:
                normalized.append(AutoGradingMessage(str(item), default_tone))
        return tuple(normalized)

    def merged_text(self) -> str:
        return "\n".join(message.text for message in self.messages if message.text and message.text.strip())

    def dominant_tone(self) -> str:
        if not self.messages:
            return "success" if self.success else "warning"
        priority = {"warning": 2, "success": 1, "info": 0}
        return max((msg.normalized_tone() for msg in self.messages), key=lambda tone: priority.get(tone, 0))


class AutoGradingRoutine(Protocol):
    def __call__(
        self,
        controller: ChromeRemoteController,
        student_name: str,
        student_id: str,
        total_points: int,
        auto_save: bool,
        context: AutoGradingSessionContext,
    ) -> AutoGradingResult | bool:
        """Perform Selenium-driven grading for a single student."""

# https://moodle.lut.fi/mod/assign/view.php?id=1835503&action=grading
# https://moodle.lut.fi/mod/assign/view.php?id=1835503&action=grading&search=003294855&userid=2277828

def run_auto_grading(
    controller: ChromeRemoteController,
    student_name: str,
    student_id: str,
    total_points: int,
    auto_save: bool,
    context: AutoGradingSessionContext,
) -> AutoGradingResult:
    try:
        driver = controller.open_browser()
    except Exception as exc:  # pragma: no cover - guard Selenium failures
        return AutoGradingResult.failure_result(
            f"Failed to open browser session: {exc}",
            should_stop=True,
        )

    assignment_id = context.assignment_id
    if assignment_id is None:
        url_testers = [
            "&action=grading",
            "moodle.lut.fi/mod/assign/view.php",
            "id=",
        ]
        current_url = driver.current_url or ""
        
        for tester in url_testers:
            if tester not in current_url:
                return AutoGradingResult.failure_result(
                    f"Expected Moodle grading page but '{tester}' was missing in the current URL.",
                    should_stop=True,
                )

        # extract id= value from url (example): https://moodle.lut.fi/mod/assign/view.php?id=1835503&action=grading
        try:
            id_value = current_url.split("id=")[1].split("&")[0]
        except (IndexError, AttributeError):  # pragma: no cover - defensive coding
            id_value = ""
        if not id_value.isdigit():
            return AutoGradingResult.failure_result(
                f"Failed to extract a numeric 'id' from URL: {current_url}",
                should_stop=True,
            )
        try:
            assignment_id = context.ensure_assignment_id(id_value)
        except ValueError as exc:
            return AutoGradingResult.failure_result(
                str(exc),
                should_stop=True,
            )

    is_confirmed = context.is_confirmed
    if is_confirmed is None:
        confirmation_message = (
            " "
            "Select 'Yes' to continue or 'No' to skip remaining students."
        )
        try:
            is_confirmed = context.ensure_confirmation(confirmation_message)
        except RuntimeError as exc:
            return AutoGradingResult.failure_result(
                str(exc),
                should_stop=True,
            )

    if not is_confirmed:
        return AutoGradingResult.failure_result(
            [
                AutoGradingMessage(
                    "Auto-grading skipped because confirmation was declined.",
                    tone="warning",
                ),
            ],
            should_stop=False,
        )

    sleep(2)
    return AutoGradingResult.failure_result(
        [
            AutoGradingMessage(
                f"Verified Moodle grading context (assignment id={assignment_id}) for {student_name or student_id}.",
                tone="info",
            ),
            AutoGradingMessage(
                "Auto-grading workflow not implemented yet. Update 'run_auto_grading' with Selenium steps.",
                tone="warning",
            ),
        ],
    )


__all__ = [
    "AutoGradingSessionContext",
    "AutoGradingMessage",
    "AutoGradingResult",
    "AutoGradingRoutine",
    "run_auto_grading",
]

