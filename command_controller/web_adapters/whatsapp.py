"""WhatsApp Web automation adapter using Playwright."""

from __future__ import annotations

from playwright.sync_api import Page, TimeoutError as PwTimeout

from command_controller.intents import WebExecutionError
from utils.log_utils import tprint

WHATSAPP_URL = "https://web.whatsapp.com"

# ---------------------------------------------------------------------------
# Selectors – isolated here so future WhatsApp DOM changes only touch this
# file.  Prefer data-* attributes and ARIA roles where possible.
# ---------------------------------------------------------------------------
SELECTORS = {
    "search_box": 'div[contenteditable="true"][data-tab="3"]',
    "message_input": 'div[contenteditable="true"][data-tab="10"]',
    "send_button": 'button[data-testid="send"]',
}

DEFAULT_TIMEOUT_MS = 15_000


def send_message(page: Page, *, contact: str, message: str) -> None:
    """Send a WhatsApp message to *contact* containing *message*.

    Raises :class:`WebExecutionError` with a structured code on failure.
    """
    if not contact:
        raise WebExecutionError(
            code="WA_MISSING_CONTACT", message="contact is required"
        )
    if not message:
        raise WebExecutionError(
            code="WA_MISSING_MESSAGE", message="message is required"
        )

    tprint(f"[WHATSAPP] Sending to '{contact}': {message!r}")

    # 1. Navigate to WhatsApp Web if not already there
    if not page.url.startswith(WHATSAPP_URL):
        page.goto(WHATSAPP_URL, wait_until="domcontentloaded")

    # 2. Wait for the search box (indicates the user is logged in)
    try:
        search_box = page.wait_for_selector(
            SELECTORS["search_box"], timeout=DEFAULT_TIMEOUT_MS
        )
    except PwTimeout:
        raise WebExecutionError(
            code="WA_NOT_LOGGED_IN",
            message="WhatsApp search box not found. User may need to scan QR code.",
        )

    # 3. Search for the contact
    search_box.click()
    search_box.fill(contact)

    try:
        contact_el = page.get_by_text(contact, exact=True).first
        contact_el.wait_for(timeout=DEFAULT_TIMEOUT_MS)
    except PwTimeout:
        raise WebExecutionError(
            code="WA_CONTACT_NOT_FOUND",
            message=f"Contact '{contact}' not found in WhatsApp.",
        )
    contact_el.click()

    # 4. Type the message
    try:
        msg_input = page.wait_for_selector(
            SELECTORS["message_input"], timeout=DEFAULT_TIMEOUT_MS
        )
    except PwTimeout:
        raise WebExecutionError(
            code="WA_CHAT_NOT_READY",
            message="Message input box not found after selecting contact.",
        )
    msg_input.click()
    msg_input.fill(message)

    # 5. Send via Enter (more reliable than clicking the send button)
    msg_input.press("Enter")
    tprint(f"[WHATSAPP] Message sent to '{contact}'")
