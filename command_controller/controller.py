"""Core controller that routes gesture and voice events to executors."""

from __future__ import annotations

import queue
import threading
import time

from command_controller.context import get_context
from command_controller.engine import CommandEngine
from command_controller.logger import CommandLogger
from utils.file_utils import load_json
from utils.log_utils import tprint
from utils.settings_store import deep_log
from video_module.gesture_ml import GestureDataset


class CommandController:
    def __init__(self, *, user_id: str = "default") -> None:
        self.logger = CommandLogger()
        self.dataset = GestureDataset(user_id=user_id)
        self.engine = CommandEngine(logger=self.logger)
        settings = load_json("config/app_settings.json")
        self.command_timeout_secs = max(0.0, settings.get("command_timeout_ms", 20000) / 1000.0)
        self._queue: queue.Queue[tuple[str, str, dict | None]] = queue.Queue(maxsize=64)
        self._worker = threading.Thread(target=self._run_worker, name="command-worker", daemon=True)
        self._worker.start()

    def start(self) -> None:
        """Placeholder for starting controller resources."""
        self.logger.info("Command controller ready")

    def handle_event(self, source: str, action: str, payload: dict | None = None) -> None:
        """Receive an event from gesture or voice modules and execute it."""
        try:
            deep_log(f"[DEEP][CTRL] enqueue source={source} action={action} payload={payload}")
            self._queue.put_nowait((source, action, payload))
        except queue.Full:
            tprint("[CTRL] Command queue full; dropping event")

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

    def _run_worker(self) -> None:
        while True:
            source, action, payload = self._queue.get()
            try:
                self._process_event(source, action, payload)
            except Exception as exc:
                self.logger.error(f"Command worker error: {exc}")
            finally:
                self._queue.task_done()

    def _process_event(self, source: str, action: str, payload: dict | None) -> None:
        payload = payload or {}
        self.logger.info(f"Received {source} action: {action}")
        if source == "gesture":
            text = self.dataset.commands.get(action, "")
            steps = self.dataset.command_steps.get(action, [])
            if not text:
                self.logger.info(f"No command mapped for gesture '{action}'")
                return
            if steps:
                deep_log(
                    "[DEEP][CTRL] run_steps "
                    f"label={action} text={text!r} steps={steps}"
                )
                result = self.engine.run_steps(source=source, text=text, steps=steps)
                self.logger.info(f"Command result: {result.get('status')}")
                return
        else:
            text = action
        read_selection = not self._is_basic_shortcut(text)
        context = get_context(read_selection=read_selection)
        deep_log(
            "[DEEP][CTRL] run_llm "
            f"source={source} text={text!r} context={context}"
        )
        result = self._run_engine_with_timeout(source=source, text=text, context=context)
        self.logger.info(f"Command result: {result.get('status')}")

    def _run_engine_with_timeout(self, *, source: str, text: str, context: dict) -> dict:
        if self.command_timeout_secs <= 0:
            return self.engine.run(source=source, text=text, context=context)
        result_holder: dict[str, dict] = {}
        error_holder: dict[str, Exception] = {}

        def _runner() -> None:
            try:
                result_holder["result"] = self.engine.run(source=source, text=text, context=context)
            except Exception as exc:
                error_holder["error"] = exc

        thread = threading.Thread(target=_runner, name="command-exec", daemon=True)
        start_ts = time.monotonic()
        thread.start()
        thread.join(timeout=self.command_timeout_secs)
        if thread.is_alive():
            elapsed_ms = int((time.monotonic() - start_ts) * 1000)
            self.logger.error(f"Command timeout after {elapsed_ms} ms")
            return {"status": "timeout", "message": "Command timed out"}
        if "error" in error_holder:
            raise error_holder["error"]
        return result_holder.get("result", {"status": "error", "message": "No result"})

    def list_pending(self) -> list[dict]:
        return self.engine.list_pending()

    def approve(self, confirmation_id: str) -> dict:
        return self.engine.approve(confirmation_id)

    def deny(self, confirmation_id: str) -> dict:
        return self.engine.deny(confirmation_id)

    def last_result(self) -> dict | None:
        return self.engine.get_last_result()
