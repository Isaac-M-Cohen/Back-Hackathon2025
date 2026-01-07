"""Core controller that routes gesture and voice events to executors."""

from __future__ import annotations

from command_controller.context import get_context
from command_controller.engine import CommandEngine
from command_controller.logger import CommandLogger
from video_module.gesture_ml import GestureDataset


class CommandController:
    def __init__(self, *, user_id: str = "default") -> None:
        self.logger = CommandLogger()
        self.dataset = GestureDataset(user_id=user_id)
        self.engine = CommandEngine(logger=self.logger)

    def start(self) -> None:
        """Placeholder for starting controller resources."""
        self.logger.info("Command controller ready")

    def handle_event(self, source: str, action: str, payload: dict | None = None) -> None:
        """Receive an event from gesture or voice modules and execute it."""
        payload = payload or {}
        self.logger.info(f"Received {source} action: {action}")
        if source == "gesture":
            text = self.dataset.commands.get(action, "")
            if not text:
                self.logger.info(f"No command mapped for gesture '{action}'")
                return
        else:
            text = action
        read_selection = not self._is_basic_shortcut(text)
        context = get_context(read_selection=read_selection)
        result = self.engine.run(source=source, text=text, context=context)
        self.logger.info(f"Command result: {result.get('status')}")

    def _is_basic_shortcut(self, text: str) -> bool:
        normalized = text.strip().lower()
        if not normalized:
            return False
        return normalized in {
            "copy",
            "copy selection",
            "copy selected text",
            "paste",
            "paste selection",
            "cut",
            "cut selection",
            "undo",
            "redo",
            "select all",
        }

    def list_pending(self) -> list[dict]:
        return self.engine.list_pending()

    def approve(self, confirmation_id: str) -> dict:
        return self.engine.approve(confirmation_id)

    def deny(self, confirmation_id: str) -> dict:
        return self.engine.deny(confirmation_id)
