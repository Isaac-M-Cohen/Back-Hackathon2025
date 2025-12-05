"""Listens for audio input and forwards recognized commands."""

from command_controller.controller import CommandController
from voice_module.stt_engine import SpeechToTextEngine


class VoiceListener:
    def __init__(self, controller: CommandController) -> None:
        self.controller = controller
        self.stt = SpeechToTextEngine()

    def start(self) -> None:
        """Begin listening (placeholder implementation)."""
        print("[VOICE] Listener initialized")
        transcription = self.stt.transcribe("open browser")
        self.controller.handle_event(source="voice", action=transcription)
