"""Core controller that routes gesture and voice events to executors."""

from command_controller.executor import Executor
from command_controller.logger import CommandLogger


class CommandController:
    def __init__(self) -> None:
        self.executor = Executor()
        self.logger = CommandLogger()

    def start(self) -> None:
        """Placeholder for starting controller resources."""
        self.logger.info("Command controller ready")

    def handle_event(self, source: str, action: str, payload: dict | None = None) -> None:
        """Receive an event from gesture or voice modules and execute it."""
        self.logger.info(f"Received {source} action: {action}")
        self.executor.execute(action, payload or {})
        self.logger.info(f"Completed {action}")
