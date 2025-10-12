from __future__ import annotations

from dataclasses import dataclass
from time import sleep
from typing import Callable, Iterable, Protocol

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from .chrome import ChromeRemoteController

_VALID_TONES = {"info", "success", "warning", "normal"}


@dataclass(slots=True)
class AutoGradingSessionContext:

    prompt_callback: Callable[[str], bool] | None = None
    assignment_id: str | None = None
    is_confirmed: bool | None = None
    log_callback: Callable[["AutoGradingMessage"], None] | None = None

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
        priority = {"warning": 3, "success": 2, "info": 1, "normal": 0}
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
    messages: list[AutoGradingMessage] = []

    def log(text: str, tone: str = "info") -> None:
        cleaned = (text or "").strip()
        if not cleaned:
            return
        message = AutoGradingMessage(cleaned, tone)
        messages.append(message)
        if context.log_callback is not None:
            try:
                context.log_callback(message)
            except Exception:  # pragma: no cover - log callbacks must not break automation
                pass

    try:
        driver = controller.open_browser()
    except Exception as exc:  # pragma: no cover - guard Selenium failures
        log(f"Failed to open browser session: {exc}", "warning")
        return AutoGradingResult(False, tuple(messages), should_stop=True)

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
                log("Expected Moodle grading page. Please go to 'All Submissions' grading page.", "warning")
                return AutoGradingResult(False, tuple(messages), should_stop=True)

        # extract id= value from url (example): https://moodle.lut.fi/mod/assign/view.php?id=1835503&action=grading
        try:
            id_value = current_url.split("id=")[1].split("&")[0]
        except (IndexError, AttributeError):  # pragma: no cover - defensive coding
            id_value = ""
        if not id_value.isdigit():
            log(f"Failed to extract a numeric 'id' from URL: {current_url}", "warning")
            return AutoGradingResult(False, tuple(messages), should_stop=True)
        try:
            assignment_id = context.ensure_assignment_id(id_value)
        except ValueError as exc:
            log(str(exc), "warning")
            return AutoGradingResult(False, tuple(messages), should_stop=True)

    grading_url = f"https://moodle.lut.fi/mod/assign/view.php?id={assignment_id}&action=grading&quickgrading=1"
    search_url = f"https://moodle.lut.fi/mod/assign/view.php?id={assignment_id}&action=grading&search={student_id}"
    
    is_confirmed = context.is_confirmed
    if is_confirmed is None:
        try:
            driver.get(grading_url)
            page_header = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.page-header-headings"))
            )
        except Exception as exc:  # pragma: no cover - guard Selenium failures
            log(f"Failed to navigate to grading page: {exc}", "warning")
            return AutoGradingResult(False, tuple(messages), should_stop=False)
        
        header_text = page_header.find_element(By.TAG_NAME, "h1").text if page_header else ""

        confirmation_message = (
            f"Is this the correct grading page for correct chapter?: {header_text} "
            "Select 'Yes' to continue or 'No' to stop grading."
        )
        try:
            is_confirmed = context.ensure_confirmation(confirmation_message)
        except RuntimeError as exc:
            log(str(exc), "warning")
            return AutoGradingResult(False, tuple(messages), should_stop=True)

    if not is_confirmed:
        log("Auto-grading stopped because confirmation was declined.", "warning")
        return AutoGradingResult(False, tuple(messages), should_stop=True)

    log(
        f"Finding student...\nStudent ID: {student_id},\nName: {student_name}",
        "info",
    )

    try:
        driver.get(search_url)
        page_header = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div.page-header-headings"))
        )
        header_text = page_header.find_element(By.TAG_NAME, "h1").text if page_header else ""
        # Wait for the search results to load table with id="submissions"
        results_table = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "table#submissions"))
        )
        # scroll to results_table
        driver.execute_script("arguments[0].scrollIntoView();", results_table)
    except Exception as exc:  
        log(f"Failed to search for student {student_id}: {exc}", "warning")
        return AutoGradingResult(False, tuple(messages), should_stop=False)

    log(
        f"Found grading page for student ID '{student_id}': {header_text}",
        "info",
    )

    try:
        result_id_number = results_table.find_element(By.CSS_SELECTOR, "td.idnumber").text.strip()
        if student_id not in result_id_number:
            log(f"Student ID '{student_id}' does not match the search results.", "warning")
            return AutoGradingResult(False, tuple(messages), should_stop=False)
    except Exception:  
        log(f"Student ID '{student_id}' not found in search results.", "warning")
        return AutoGradingResult(False, tuple(messages), should_stop=False)
    
    try:
        grade_cell = results_table.find_element(By.CSS_SELECTOR, "td.grade")
        grade_input = grade_cell.find_element(By.CSS_SELECTOR, "input[type='text'][class='quickgrade']")
    except Exception:  
        log(f"Failed to find grade input grading cell for student ID '{student_id}'.", "warning")
        return AutoGradingResult(False, tuple(messages), should_stop=False)
    
    try:
        # get current value
        current_value = grade_input.get_attribute("value")
        # check if the cell is empty or not
        if current_value and current_value.strip():
            log(
                f"Grade input for student ID '{student_id}' is not empty (current value: '{current_value}'). Skipping entry.",
                "warning",
            )
            sleep(1)
            return AutoGradingResult(False, tuple(messages), should_stop=False)
        
        grade_input.clear()
        grade_input.send_keys(str(total_points))
        log(
            f"Entered grade {total_points} for student ID '{student_id}'. Waiting to save...",
            "info",
        )
    except Exception:  
        log(f"Failed to enter grade for student ID '{student_id}'.", "warning")
        return AutoGradingResult(False, tuple(messages), should_stop=False)
    
    if auto_save:
        try:
            save_button_region = driver.find_element(By.CSS_SELECTOR, "div[data-region='quick-grading-save']")
            save_button = save_button_region.find_element(By.CSS_SELECTOR, "button[type='submit']")
            
            if not save_button.text.strip().lower().startswith("save"):
                log(
                    f"Could not find a 'Save' button to auto-save grade for student ID '{student_id}'.",
                    "warning",
                )
                return AutoGradingResult(False, tuple(messages), should_stop=False)
            

            current_url = driver.current_url
            save_button.click()
            try:
                WebDriverWait(driver, 180).until(EC.url_changes(current_url))
            except TimeoutException:
                log(
                    f"Timed out waiting for user to save after entering grade for student ID '{student_id}'.",
                    "warning",
                )
                return AutoGradingResult(False, tuple(messages), should_stop=False)
            
            # highlight the button instead of clicking
            # driver.execute_script("arguments[0].style.border='3px solid yellow'", save_button)
            sleep(1)  

            log(
                f"Auto-saved grade for student ID '{student_id}'",
                "info",
            )
        except Exception:  
            log(f"Failed to auto-save grade for student ID '{student_id}'.", "warning")
            return AutoGradingResult(False, tuple(messages), should_stop=False)
    else:
        log(
            f"Grade entry for student ID '{student_id}' is ready. Please save manually.",
            "info",
        )
        # wait for the current_url to change (indicating a save or navigation)
        current_url = driver.current_url
        try:
            WebDriverWait(driver, 180).until(EC.url_changes(current_url))
        except TimeoutException:
            log(
                f"Timed out waiting for user to save after entering grade for student ID '{student_id}'.",
                "warning",
            )
            return AutoGradingResult(False, tuple(messages), should_stop=False)

    sleep(1)
    log(
        f"{header_text} | Grading completed\n{student_name} | {student_id}\nTotal Points: {total_points}",
        "success",
    )
    return AutoGradingResult(True, tuple(messages), should_stop=False)


__all__ = [
    "AutoGradingSessionContext",
    "AutoGradingMessage",
    "AutoGradingResult",
    "AutoGradingRoutine",
    "run_auto_grading",
]

