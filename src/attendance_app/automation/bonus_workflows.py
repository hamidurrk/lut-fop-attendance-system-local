from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from attendance_app.automation.chrome import ChromeRemoteController


@dataclass(slots=True)
class BonusAutomationResult:
    handler_name: str
    success: bool
    summary: str
    details: Optional[str] = None
    payload: Optional[Mapping[str, Any]] = None

    @classmethod
    def success_result(
        cls,
        handler_name: str,
        summary: str,
        *,
        details: Optional[str] = None,
        payload: Optional[Mapping[str, Any]] = None,
    ) -> "BonusAutomationResult":
        return cls(
            handler_name=handler_name,
            success=True,
            summary=summary,
            details=details,
            payload=payload,
        )

    @classmethod
    def failure_result(
        cls,
        handler_name: str,
        summary: str,
        *,
        details: Optional[str] = None,
        payload: Optional[Mapping[str, Any]] = None,
    ) -> "BonusAutomationResult":
        return cls(
            handler_name=handler_name,
            success=False,
            summary=summary,
            details=details,
            payload=payload,
        )

    def formatted_lines(self) -> list[str]:
        lines = [self.summary]
        if self.details:
            lines.extend(detail.strip() for detail in self.details.splitlines() if detail.strip())
        return lines


BonusAutomationHandler = Callable[[ChromeRemoteController], BonusAutomationResult]


def open_moodle_courses(controller: ChromeRemoteController) -> BonusAutomationResult:
    """Navigate the remote Chrome session to the Moodle course dashboard."""

    handler_name = "open_moodle_courses"

    try:
        driver = controller.open_browser()
        driver.get("https://moodle.lut.fi/my/courses.php")
    except Exception as exc:  # pragma: no cover - guard Selenium failures
        return BonusAutomationResult.failure_result(
            handler_name,
            "Failed to open Moodle courses page.",
            details=str(exc),
        )

    return BonusAutomationResult.success_result(
        handler_name,
        "Opened Moodle courses dashboard in Chrome.",
    )


def get_bonus_student_data(controller: ChromeRemoteController) -> BonusAutomationResult:
    handler_name = "get_bonus_student_data"
    
    try:
        driver = controller.open_browser()
        try:
        # Chrome DevTools Protocol to get info about all tabs
            targets = driver.execute_cdp_cmd('Target.getTargets', {})
            
            tab_info = []
            if 'targetInfos' in targets:
                for target in targets['targetInfos']:
                    if target.get('type') == 'page':
                        tab_info.append({
                            'title': target.get('title', 'Unknown'),
                            'url': target.get('url', 'Unknown'),
                            'targetId': target.get('targetId')
                        })
        except Exception as e:
            return BonusAutomationResult.failure_result(
                handler_name,
                "Could not find codegrade tab via CDP. Please contact the developer.",
            )

        selected_tab = None
        for info in tab_info:
            if "codegra" in info['url'] or "codegrade" in info['url'] or ("CodeGrade" in info['title'] and "Submission" in info['title']) or "CodeGrade" in info['title']:
                selected_tab = info
                break

        if not selected_tab:
            return BonusAutomationResult.failure_result(
                handler_name,
                "Could not find codegrade tab via keywords. Please contact the developer.",
            )
        
        driver.switch_to.window(selected_tab['targetId'])
        
        selector_btn = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '[data-cy="submission-selector-btn"]'))
        )
        
        name_span = selector_btn.find_element(By.CSS_SELECTOR, 'span.name-user')
        
        student_name = name_span.text.strip()
        if not student_name:
            return BonusAutomationResult.failure_result(
                handler_name,
                "Found student element but it contains no text"
            )
            
        return BonusAutomationResult.success_result(
            handler_name,
            f"Found student: {student_name}",
            payload={"student_name": student_name}
        )
        
    except TimeoutException:
        return BonusAutomationResult.failure_result(
            handler_name,
            "Timed out waiting for submission selector button to appear"
        )
    except NoSuchElementException:
        return BonusAutomationResult.failure_result(
            handler_name,
            "Could not find student name element with class 'name-user'"
        )
    except Exception as exc:
        return BonusAutomationResult.failure_result(
            handler_name,
            "Error extracting student data",
            details=str(exc)
        )

__all__ = [
    "BonusAutomationHandler",
    "BonusAutomationResult",
    "get_bonus_student_data",
    "open_moodle_courses",
]
