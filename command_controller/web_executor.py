"""Playwright-based executor for web-target intents."""

from __future__ import annotations

import os
import time
from pathlib import Path

from command_controller.intents import WebExecutionError
from utils.log_utils import tprint
from utils.settings_store import get_settings, is_deep_logging, deep_log


class WebExecutor:
    """Manages a persistent Playwright browser and dispatches web intents."""

    def __init__(self) -> None:
        self._playwright = None
        self._browser = None
        self._page = None
        self._initialized = False

    # ------------------------------------------------------------------
    # Lazy initialisation
    # ------------------------------------------------------------------

    def _ensure_browser(self) -> None:
        """Launch a persistent Chromium context on first call."""
        if self._initialized:
            return

        from playwright.sync_api import sync_playwright

        settings = get_settings()
        profile_dir = settings.get(
            "playwright_profile_dir",
            os.path.join("user_data", "playwright_profile"),
        )
        headless = settings.get("playwright_headless", False)

        Path(profile_dir).mkdir(parents=True, exist_ok=True)

        self._playwright = sync_playwright().start()
        try:
            self._browser = self._playwright.chromium.launch_persistent_context(
                user_data_dir=profile_dir,
                headless=headless,
                accept_downloads=False,
            )
        except Exception as exc:
            self._playwright.stop()
            self._playwright = None
            raise RuntimeError(
                f"Failed to launch browser: {exc}\n"
                "If Chromium is not installed, run: playwright install chromium"
            ) from exc
        self._page = (
            self._browser.pages[0]
            if self._browser.pages
            else self._browser.new_page()
        )
        self._initialized = True
        tprint("[WEB_EXEC] Playwright browser context initialized")

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def execute_step(self, step: dict) -> None:
        """Route a single web-target step to the appropriate adapter."""
        intent = step.get("intent")
        try:
            self._ensure_browser()

            if intent == "web_send_message":
                self._handle_send_message(step)
            else:
                tprint(f"[WEB_EXEC] Unknown web intent '{intent}'")
        except WebExecutionError:
            raise
        except Exception as exc:
            screenshot_path = self._save_error_screenshot(intent or "unknown")
            raise WebExecutionError(
                code="WEB_UNEXPECTED",
                message=str(exc),
                screenshot_path=screenshot_path,
            ) from exc

    # ------------------------------------------------------------------
    # Intent handlers
    # ------------------------------------------------------------------

    def _handle_send_message(self, step: dict) -> None:
        from command_controller.web_adapters.whatsapp import send_message

        contact = step.get("contact", "")
        message = step.get("message", "")

        if is_deep_logging():
            deep_log(
                f"[DEEP][WEB_EXEC] web_send_message contact={contact!r} message={message!r}"
            )

        send_message(self._page, contact=contact, message=message)

    # ------------------------------------------------------------------
    # Error handling helpers
    # ------------------------------------------------------------------

    def _save_error_screenshot(self, intent: str) -> str | None:
        try:
            screenshots_dir = Path("user_data", "error_screenshots")
            screenshots_dir.mkdir(parents=True, exist_ok=True)
            ts = int(time.time())
            path = str(screenshots_dir / f"{intent}_{ts}.png")
            if self._page and not self._page.is_closed():
                self._page.screenshot(path=path)
                tprint(f"[WEB_EXEC] Error screenshot saved: {path}")
                return path
        except Exception as ss_exc:
            tprint(f"[WEB_EXEC] Failed to save screenshot: {ss_exc}")
        return None

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def shutdown(self) -> None:
        """Close browser and Playwright."""
        if self._browser:
            try:
                self._browser.close()
            except Exception:
                pass
        if self._playwright:
            try:
                self._playwright.stop()
            except Exception:
                pass
        self._initialized = False
        self._browser = None
        self._page = None
        self._playwright = None
