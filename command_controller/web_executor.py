"""Playwright-based executor for web-target intents."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING

from command_controller.intents import WebExecutionError
from utils.log_utils import tprint
from utils.settings_store import get_settings, is_deep_logging, deep_log

if TYPE_CHECKING:
    from command_controller.fallback_chain import FallbackResult


class WebExecutor:
    """Manages a persistent Playwright browser and dispatches web intents."""

    def __init__(self) -> None:
        self._playwright = None
        self._browser = None
        self._page = None
        self._initialized = False

        # Lazy initialization for URL resolution
        self._url_resolver = None
        self._fallback_chain = None
        self._last_resolution = None

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

            if intent == "open_url":
                self._handle_open_url(step)
            elif intent == "type_text":
                self._handle_type_text(step)
            elif intent == "key_combo":
                self._handle_key_combo(step)
            elif intent == "click":
                self._handle_click(step)
            elif intent == "scroll":
                self._handle_scroll(step)
            elif intent == "web_send_message":
                self._handle_send_message(step)
            elif intent == "web_fill_form":
                self._handle_form_fill(step)
            elif intent == "web_request_permission":
                self._handle_request_permission(step)
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

    def _handle_open_url(self, step: dict) -> None:
        """Enhanced open_url handler with resolution and fallback."""
        url = step.get("url", "")
        settings = get_settings()

        # Check if enhanced web flow is enabled
        if not settings.get("use_playwright_for_web", True):
            # Legacy path: direct navigation in Playwright
            if is_deep_logging():
                deep_log(f"[DEEP][WEB_EXEC] Legacy path: open_url url={url}")
            self._page.goto(url, wait_until="domcontentloaded")
            self._page.wait_for_load_state("networkidle")
            tprint(f"[WEB_EXEC] Navigated to {url}")
            return

        # Enhanced path: URL resolution + fallback
        if is_deep_logging():
            deep_log(f"[DEEP][WEB_EXEC] Enhanced path: resolving url={url}")

        fallback_chain = self._get_fallback_chain()
        result = fallback_chain.execute(url)

        if result.status == "all_failed":
            raise WebExecutionError(
                code="WEB_RESOLUTION_FAILED",
                message=f"Failed to resolve URL: {url}",
            )

        final_url = result.final_url

        # Security: validate URL scheme
        if not self._is_safe_url(final_url):
            raise WebExecutionError(
                code="WEB_UNSAFE_URL",
                message=f"Resolved URL has unsafe scheme: {final_url}",
            )

        # Confirmation check (stub for now)
        if settings.get("request_before_open_url", False):
            tprint(f"[WEB_EXEC] Opening URL in default browser: {final_url}")

        # Open in default browser (macOS)
        # Use "--" to prevent flag injection from crafted URLs
        try:
            subprocess.run(
                ["open", "--", final_url],
                check=True,
                capture_output=True,
                timeout=10
            )
            tprint(f"[WEB_EXEC] Opened {final_url} in default browser")
        except subprocess.TimeoutExpired:
            raise WebExecutionError(
                code="WEB_OPEN_TIMEOUT",
                message=f"Timeout opening URL: {final_url}"
            )
        except subprocess.CalledProcessError as exc:
            raise WebExecutionError(
                code="WEB_OPEN_FAILED",
                message=f"Failed to open URL: {exc.stderr.decode() if exc.stderr else str(exc)}"
            )

        # Store metadata for ExecutionResult enrichment
        self._last_resolution = result

    def get_last_resolution(self) -> FallbackResult | None:
        """Return metadata from the most recent URL resolution.

        This method implements the ResolutionMetadataProvider protocol.
        """
        return self._last_resolution

    def _handle_type_text(self, step: dict) -> None:
        text = step.get("text", "")
        selector = step.get("selector")
        if is_deep_logging():
            deep_log(f"[DEEP][WEB_EXEC] type_text text={text!r} selector={selector!r}")
        if selector:
            el = self._page.wait_for_selector(selector, timeout=10000)
            el.click()
            el.type(text)
        else:
            self._page.keyboard.type(text)

    def _handle_key_combo(self, step: dict) -> None:
        keys = step.get("keys", [])
        if is_deep_logging():
            deep_log(f"[DEEP][WEB_EXEC] key_combo keys={keys}")
        pw_keys = [self._to_playwright_key(k) for k in keys]
        combo = "+".join(pw_keys)
        self._page.keyboard.press(combo)

    def _handle_click(self, step: dict) -> None:
        selector = step.get("selector")
        x = step.get("x")
        y = step.get("y")
        button = step.get("button", "left")
        clicks = step.get("clicks", 1)
        if is_deep_logging():
            deep_log(f"[DEEP][WEB_EXEC] click selector={selector!r} x={x} y={y}")
        if selector:
            el = self._page.wait_for_selector(selector, timeout=10000)
            el.click(button=button, click_count=clicks)
        elif x is not None and y is not None:
            self._page.mouse.click(float(x), float(y), button=button, click_count=clicks)
        else:
            self._page.mouse.click(0, 0, button=button, click_count=clicks)

    def _handle_scroll(self, step: dict) -> None:
        direction = step.get("direction", "down")
        amount = step.get("amount", 3)
        delta = amount * 100 if direction == "down" else -(amount * 100)
        if is_deep_logging():
            deep_log(f"[DEEP][WEB_EXEC] scroll direction={direction} amount={amount}")
        self._page.mouse.wheel(0, delta)

    @staticmethod
    def _to_playwright_key(key: str) -> str:
        mapping = {
            "cmd": "Meta",
            "command": "Meta",
            "ctrl": "Control",
            "control": "Control",
            "alt": "Alt",
            "option": "Alt",
            "opt": "Alt",
            "shift": "Shift",
            "enter": "Enter",
            "return": "Enter",
            "esc": "Escape",
            "escape": "Escape",
            "tab": "Tab",
            "space": " ",
            "backspace": "Backspace",
            "delete": "Delete",
            "up": "ArrowUp",
            "down": "ArrowDown",
            "left": "ArrowLeft",
            "right": "ArrowRight",
        }
        return mapping.get(key.lower(), key)

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
    # URL resolution helpers
    # ------------------------------------------------------------------

    def _get_url_resolver(self):
        """Lazy initialize URL resolver with separate headless context."""
        if self._url_resolver is None:
            from command_controller.url_resolver import URLResolver

            self._url_resolver = URLResolver()
            # Eagerly warm up browser to amortize initialization cost
            # This is safe because URLResolver uses a separate profile
            settings = get_settings()
            if settings.get("warmup_url_resolver", True):
                try:
                    self._url_resolver.warmup()
                except Exception as exc:
                    tprint(f"[WEB_EXEC] URL resolver warm-up failed: {exc}")
        return self._url_resolver

    def _get_fallback_chain(self):
        """Lazy initialize fallback chain."""
        if self._fallback_chain is None:
            from command_controller.fallback_chain import FallbackChain

            resolver = self._get_url_resolver()
            self._fallback_chain = FallbackChain(resolver)
        return self._fallback_chain

    def _handle_form_fill(self, step: dict) -> None:
        """Fill web forms using Playwright (gated by config)."""
        settings = get_settings()
        if not settings.get("allow_headless_form_fill", False):
            raise WebExecutionError(
                code="WEB_FORM_FILL_DISABLED",
                message="Form fill is disabled. Enable via allow_headless_form_fill config.",
            )

        form_fields = step.get("form_fields", {})
        submit = step.get("submit", False)

        if is_deep_logging():
            deep_log(
                f"[DEEP][WEB_EXEC] web_fill_form fields={list(form_fields.keys())} submit={submit}"
            )

        for selector, value in form_fields.items():
            try:
                el = self._page.wait_for_selector(selector, timeout=10000)
                el.fill(str(value))
            except Exception as exc:
                raise WebExecutionError(
                    code="WEB_FORM_FIELD_NOT_FOUND",
                    message=f"Field '{selector}' not found: {exc}",
                ) from exc

        if submit:
            try:
                submit_btn = self._page.locator(
                    'button[type="submit"], input[type="submit"]'
                ).first
                submit_btn.click()
            except Exception as exc:
                raise WebExecutionError(
                    code="WEB_FORM_SUBMIT_FAILED",
                    message=f"Submit failed: {exc}",
                ) from exc

        tprint("[WEB_EXEC] Form filled successfully")

    def _handle_request_permission(self, step: dict) -> None:
        """Permission hook stub (Milestone 6)."""
        permission_type = step.get("permission_type", "")
        tprint(f"[WEB_EXEC] Permission requested: {permission_type}")
        # Stub implementation - future integration with browser permission APIs

    @staticmethod
    def _is_safe_url(url: str | None) -> bool:
        """Validate URL is safe to open in browser.

        Checks:
        - URL exists and has reasonable length
        - Scheme is http or https
        - Not localhost/loopback
        - Not private IP ranges
        - Not cloud metadata service
        """
        if not url:
            return False

        # Length check (prevent DoS)
        if len(url) > 2048:
            return False

        from urllib.parse import urlparse
        import ipaddress

        try:
            parsed = urlparse(url)
        except Exception:
            return False

        # Scheme validation
        if parsed.scheme not in ("http", "https"):
            return False

        # Hostname validation
        hostname = parsed.hostname
        if not hostname:
            return False

        # Block localhost
        if hostname in ("localhost", "127.0.0.1", "::1"):
            return False

        # Block private IPs and metadata service
        try:
            ip = ipaddress.ip_address(hostname)
            if ip.is_private or ip.is_loopback or ip.is_link_local:
                return False
            # Block cloud metadata service
            if str(ip) == "169.254.169.254":
                return False
        except ValueError:
            # Not an IP address, hostname validation passed
            pass

        return True

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def shutdown(self) -> None:
        """Close browser, Playwright, and URL resolver."""
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

        # Cleanup URL resolver
        if self._url_resolver:
            try:
                self._url_resolver.shutdown()
            except Exception:
                pass

        self._initialized = False
        self._browser = None
        self._page = None
        self._playwright = None
        self._url_resolver = None
        self._fallback_chain = None
        self._last_resolution = None
