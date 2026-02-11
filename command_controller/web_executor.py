"""Playwright-based executor for web-target intents."""

from __future__ import annotations

import os
import subprocess
import time
import threading
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import quote_plus, urlparse

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
        self._playwright_thread_id: int | None = None
        self._defer_open_default = False
        self._pending_search_text: str | None = None
        self._last_open_url: str | None = None
        self._playwright_available = True
        self._missing_playwright = False
        self._missing_playwright_reason: str | None = None
        self._fallback_base_url: str | None = None
        self._fallback_search_text: str | None = None

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
            current_thread_id = threading.get_ident()
            if self._playwright_thread_id != current_thread_id:
                tprint(
                    "[WEB_EXEC] Playwright initialized on different thread; restarting browser context."
                )
                self._shutdown_browser()
            else:
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
        self._playwright_thread_id = threading.get_ident()
        tprint("[WEB_EXEC] Playwright browser context initialized")

    def _shutdown_browser(self) -> None:
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
        self._browser = None
        self._page = None
        self._playwright = None
        self._initialized = False
        self._playwright_thread_id = None

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def execute_step(self, step: dict) -> None:
        """Route a single web-target step to the appropriate adapter."""
        intent = step.get("intent")
        try:
            if intent == "open_url" and step.get("resolved_url"):
                self._handle_open_url(step)
                return
            if not self._playwright_available:
                if self._missing_playwright:
                    raise WebExecutionError(
                        code="WEB_PLAYWRIGHT_MISSING",
                        message=self._missing_playwright_reason
                        or "Playwright not installed. Install with: pip install playwright && playwright install chromium",
                    )
                self._handle_web_fallback(step)
                return
            try:
                self._ensure_browser()
            except ModuleNotFoundError:
                self._playwright_available = False
                self._missing_playwright = True
                self._missing_playwright_reason = (
                    "Playwright not installed. Install with: pip install playwright && playwright install chromium"
                )
                tprint("[WEB_EXEC] Playwright not installed; refusing to run web automation.")
                raise WebExecutionError(
                    code="WEB_PLAYWRIGHT_MISSING",
                    message=self._missing_playwright_reason,
                )
            except RuntimeError as exc:
                msg = str(exc).lower()
                if "playwright" in msg or "chromium" in msg or "install" in msg:
                    self._playwright_available = False
                    self._missing_playwright = True
                    self._missing_playwright_reason = (
                        "Playwright/Chromium unavailable. Install with: playwright install chromium"
                    )
                    tprint("[WEB_EXEC] Playwright unavailable; refusing to run web automation.")
                    raise WebExecutionError(
                        code="WEB_PLAYWRIGHT_MISSING",
                        message=self._missing_playwright_reason,
                    )
                raise

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
        resolved_url = step.get("resolved_url")
        settings = get_settings()

        if resolved_url:
            if step.get("precomputed"):
                tprint(f"[WEB_EXEC] Using precomputed URL: {resolved_url}")
            if settings.get("request_before_open_url", False):
                tprint(f"[WEB_EXEC] Opening URL in default browser: {resolved_url}")
            try:
                self._open_default_browser(resolved_url)
                self._last_open_url = resolved_url
                return
            except WebExecutionError as exc:
                # Fallback: if precomputed URL fails, try original URL
                tprint(f"[WEB_EXEC] Precomputed URL failed ({exc.code}), falling back to original URL: {url}")
                if url and url != resolved_url:
                    try:
                        self._open_default_browser(url)
                        self._last_open_url = url
                        return
                    except WebExecutionError:
                        pass
                raise

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
        else:
            tprint("[WEB_EXEC] No precomputed URL, resolving dynamically")

        result = None
        final_url = None
        if self._is_absolute_url(url):
            final_url = url
        else:
            fallback_chain = self._get_fallback_chain()
            result = fallback_chain.execute(url)

            if result.status == "all_failed":
                tprint("[WEB_EXEC] Precomputed URL failed, falling back to resolution")
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

        if step.get("defer_open"):
            self._page.goto(final_url, wait_until="domcontentloaded")
            try:
                self._page.wait_for_load_state("domcontentloaded", timeout=4000)
            except Exception:
                pass
            self._defer_open_default = True
            self._pending_search_text = None
            self._last_open_url = final_url
            tprint(f"[WEB_EXEC] Deferred open for {final_url}")
        else:
            self._open_default_browser(final_url)

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
            try:
                el = self._page.wait_for_selector(selector, timeout=8000)
                el.click()
                el.type(text)
                self._pending_search_text = text
                return
            except Exception:
                pass
        for fallback in (
            'input[type="search"]',
            'input[name*="search" i]',
            'input[name="q"]',
            'input[aria-label*="search" i]',
            'input[placeholder*="search" i]',
            'input[id*="search" i]',
        ):
            try:
                el = self._page.wait_for_selector(fallback, timeout=4000)
                el.click()
                el.type(text)
                self._pending_search_text = text
                return
            except Exception:
                continue
        self._pending_search_text = text
        self._page.keyboard.type(text)

    def _handle_key_combo(self, step: dict) -> None:
        keys = step.get("keys", [])
        if is_deep_logging():
            deep_log(f"[DEEP][WEB_EXEC] key_combo keys={keys}")
        pw_keys = [self._to_playwright_key(k) for k in keys]
        combo = "+".join(pw_keys)
        self._page.keyboard.press(combo)
        if self._defer_open_default and any(k.lower() in {"enter", "return"} for k in keys):
            before = self._page.url
            try:
                self._page.wait_for_load_state("domcontentloaded", timeout=4000)
            except Exception:
                pass
            after = self._page.url
            if after and after != before:
                self._open_default_browser(after)
                self._defer_open_default = False
                return
            if self._pending_search_text and self._last_open_url:
                if self._try_search_url_patterns(self._last_open_url, self._pending_search_text):
                    self._defer_open_default = False
                    return
            if self._last_open_url:
                self._open_default_browser(self._last_open_url)
            self._defer_open_default = False

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

    def flush_deferred_open(self) -> None:
        if not self._defer_open_default:
            if self._fallback_base_url:
                self._open_default_browser(self._fallback_base_url)
                self._fallback_base_url = None
            return
        if self._page and self._page.url:
            self._open_default_browser(self._page.url)
        elif self._last_open_url:
            self._open_default_browser(self._last_open_url)
        self._defer_open_default = False

    def _open_default_browser(self, url: str) -> None:
        if not url:
            return
        try:
            subprocess.run(
                ["open", "--", url],
                check=True,
                capture_output=True,
                timeout=10
            )
            tprint(f"[WEB_EXEC] Opened {url} in default browser")
        except subprocess.TimeoutExpired:
            raise WebExecutionError(
                code="WEB_OPEN_TIMEOUT",
                message=f"Timeout opening URL: {url}"
            )
        except subprocess.CalledProcessError as exc:
            raise WebExecutionError(
                code="WEB_OPEN_FAILED",
                message=f"Failed to open URL: {exc.stderr.decode() if exc.stderr else str(exc)}"
            )
        finally:
            self._pending_search_text = None
            self._last_open_url = None
            self._fallback_search_text = None
            self._fallback_base_url = None

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

    @staticmethod
    def _is_absolute_url(url: str | None) -> bool:
        if not url:
            return False
        try:
            parsed = urlparse(url)
        except Exception:
            return False
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)

    def _try_search_url_patterns(self, base_url: str, query: str) -> bool:
        """Try common search URL patterns and open the first that loads."""
        if not base_url or not query:
            return False
        parsed = urlparse(base_url)
        if not parsed.scheme or not parsed.netloc:
            return False
        origin = f"{parsed.scheme}://{parsed.netloc}"
        encoded = quote_plus(query)
        patterns = [
            f"{origin}/search?q={encoded}",
            f"{origin}/search?query={encoded}",
            f"{origin}/search?term={encoded}",
            f"{origin}/results?search_query={encoded}",
            f"{origin}/results?q={encoded}",
            f"{origin}/?q={encoded}",
            f"{origin}/?query={encoded}",
        ]
        for candidate in patterns:
            try:
                if is_deep_logging():
                    deep_log(f"[DEEP][WEB_EXEC] try search url={candidate}")
                self._page.goto(candidate, wait_until="domcontentloaded", timeout=8000)
                self._open_default_browser(candidate)
                return True
            except Exception:
                continue
        return False

    def _handle_web_fallback(self, step: dict) -> None:
        """Fallback flow when Playwright is unavailable."""
        intent = step.get("intent")
        if intent == "open_url":
            url = str(step.get("url", "")).strip()
            if not url:
                return
            if step.get("defer_open"):
                self._fallback_base_url = url
                return
            self._open_default_browser(url)
            return
        if intent == "type_text":
            text = str(step.get("text", "")).strip()
            if text:
                self._fallback_search_text = text
            return
        if intent == "key_combo":
            keys = step.get("keys") or []
            keys_lower = {str(k).lower() for k in keys}
            if "enter" not in keys_lower and "return" not in keys_lower:
                return
            base_url = self._fallback_base_url
            query = self._fallback_search_text
            if base_url and query:
                search_url = self._build_search_url(base_url, query)
                if search_url:
                    self._open_default_browser(search_url)
                    return
            if base_url:
                self._open_default_browser(base_url)
            return

    @staticmethod
    def _build_search_url(base_url: str, query: str) -> str | None:
        if not base_url or not query:
            return None
        parsed = urlparse(base_url)
        if not parsed.scheme or not parsed.netloc:
            return None
        origin = f"{parsed.scheme}://{parsed.netloc}"
        encoded = quote_plus(query)
        candidates = [
            f"{origin}/search?q={encoded}",
            f"{origin}/search?query={encoded}",
            f"{origin}/search?term={encoded}",
            f"{origin}/results?search_query={encoded}",
            f"{origin}/results?q={encoded}",
            f"{origin}/?q={encoded}",
            f"{origin}/?query={encoded}",
        ]
        return candidates[0] if candidates else None

    @staticmethod
    def _build_search_candidates(base_url: str, query: str) -> str | None:
        """Return the most likely search URL for a base origin."""
        return WebExecutor._build_search_url(base_url, query)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def shutdown(self) -> None:
        """Close browser, Playwright, and URL resolver."""
        self._shutdown_browser()

        # Cleanup URL resolver
        if self._url_resolver:
            try:
                self._url_resolver.shutdown()
            except Exception:
                pass

        self._url_resolver = None
        self._fallback_chain = None
        self._last_resolution = None

    def warmup_for_steps(self, steps: list[dict]) -> None:
        """Warm the Playwright browser for web intents without navigation."""
        if not any(
            (step.get("target") == "web")
            or str(step.get("intent", "")).startswith("web_")
            for step in steps
        ):
            return
        self._ensure_browser()
        tprint("[WEB_EXEC] Warmed browser for web intents")

    def resolve_web_steps(self, steps: list[dict]) -> dict:
        """Resolve a web command into a direct URL for instant execution."""
        open_step = None
        query_step = None
        key_step = None
        for step in steps:
            if step.get("intent") == "open_url" and (
                step.get("target") in (None, "web")
            ):
                open_step = step
            elif step.get("intent") == "type_text" and (
                step.get("target") in (None, "web")
            ):
                query_step = step
            elif step.get("intent") == "key_combo" and (
                step.get("target") in (None, "web")
            ):
                key_step = step

        if not open_step or not query_step or not key_step:
            return {}

        url = str(open_step.get("url") or "").strip()
        query = str(query_step.get("text") or "").strip()
        if not url or not query:
            return {}

        try:
            self._ensure_browser()
        except Exception as exc:
            tprint(f"[WEB_EXEC] Resolve warm-up failed: {exc}")
            return {}

        try:
            self._page.goto(url, wait_until="domcontentloaded")
            try:
                self._page.wait_for_load_state("domcontentloaded", timeout=4000)
            except Exception:
                pass
            base_url = self._page.url or url
        except Exception as exc:
            tprint(f"[WEB_EXEC] Resolve navigation failed: {exc}")
            return {}

        search_url = self._build_search_candidates(base_url, query)
        if not search_url:
            return {}

        return {
            "resolved_url": search_url,
            "base_url": base_url,
            "query": query,
        }
