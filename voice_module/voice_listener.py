"""Listens for audio input and forwards recognized commands."""
import asyncio
import base64
import threading
import time
from typing import AsyncIterable

from command_controller.controller import CommandController
from utils.log_utils import tprint
from utils.file_utils import load_json
from voice_module.stt_engine import SpeechToTextEngine


class VoiceListener:
    def __init__(
        self,
        controller: CommandController,
        listen_seconds: float | None = 5.0,
        chunk_size: int = 4096,
        single_batch: bool = False,
        log_token_usage: bool = False,
    ) -> None:
        self.controller = controller
        self.stt = SpeechToTextEngine()
        self.listen_seconds = listen_seconds
        self.chunk_size = chunk_size
        self.single_batch = single_batch
        self.log_token_usage = log_token_usage
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._single_batch_done = False

    def start(self) -> None:
        """Begin microphone capture in a background thread and stream to STT in batches."""
        if self._thread and self._thread.is_alive():
            tprint("[VOICE] Listener already running")
            return
        self._stop_event.clear()
        self._single_batch_done = False

        def _runner() -> None:
            try:
                if self.single_batch:
                    asyncio.run(
                        self.listen_and_handle_microphone(
                            seconds=self.listen_seconds or 0,
                            chunk_size=self.chunk_size,
                        )
                    )
                else:
                    asyncio.run(self._continuous_loop())
            except Exception as exc:  # pragma: no cover - surface runtime issues
                tprint(f"[VOICE] Listener error: {exc}")
            finally:
                self._single_batch_done = True
                self._stop_event.set()
                # Mark thread as finished so is_running reflects completion.
                self._thread = None

        tprint("[VOICE] Listener starting (mic -> realtime STT)...")
        self._thread = threading.Thread(
            target=_runner, name="VoiceListenerMic", daemon=False
        )
        self._thread.start()

    def stop(self) -> None:
        """Signal the listener to stop after the current batch."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None

    def is_running(self) -> bool:
        if self.single_batch and self._single_batch_done:
            return False
        return bool(self._thread and self._thread.is_alive())

    async def handle_audio_stream(self, audio_stream: AsyncIterable[bytes | str]) -> None:
        """Consume an audio stream and forward realtime transcripts."""
        transcription = await self.stt.transcribe_stream(audio_stream)
        tprint(f"[VOICE] Transcript: {transcription}")
        if self.log_token_usage:
            usage = self.stt.format_usage()
            if usage:
                tprint(f"[VOICE] Token usage: {usage}")
        self.controller.handle_event(source="voice", action=transcription)

    async def microphone_stream(
        self,
        seconds: float = 5.0,
        chunk_size: int = 4096,
        sample_rate: int | None = None,
    ) -> AsyncIterable[str]:
        """Capture microphone audio with PyAudio and yield base64-encoded chunks."""
        import pyaudio  # Lazy import to avoid hard dependency when unused.

        pa = pyaudio.PyAudio()
        rate = sample_rate or self.stt.default_sample_rate
        input_device_index = self._resolve_microphone_device_index()
        stream = pa.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=rate,
            input=True,
            frames_per_buffer=chunk_size,
            input_device_index=input_device_index,
        )

        end_time = time.time() + seconds if seconds > 0 else None
        try:
            while end_time is None or time.time() < end_time:
                data = await asyncio.to_thread(
                    stream.read, chunk_size, exception_on_overflow=False
                )
                if not data:
                    continue
                yield base64.b64encode(data).decode("ascii")
        finally:
            stream.stop_stream()
            stream.close()
            pa.terminate()

    def _resolve_microphone_device_index(self) -> int | None:
        settings = load_json("config/app_settings.json")
        value = settings.get("microphone_device_index")
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    async def listen_and_handle_microphone(
        self, seconds: float = 5.0, chunk_size: int = 4096
    ) -> None:
        """Helper to stream mic audio to STT and dispatch the transcript."""
        audio_stream = self.microphone_stream(seconds=seconds, chunk_size=chunk_size)
        transcription = await self.stt.transcribe_stream(audio_stream)
        tprint(f"[VOICE] Transcript: {transcription}")
        if self.log_token_usage:
            usage = self.stt.format_usage()
            if usage:
                tprint(f"[VOICE] Token usage: {usage}")
        self.controller.handle_event(source="voice", action=transcription)

    async def _continuous_loop(self) -> None:
        """Continuously capture mic audio in batches and send to STT."""
        batch_seconds = self.listen_seconds if self.listen_seconds and self.listen_seconds > 0 else 5.0
        while not self._stop_event.is_set():
            await self.listen_and_handle_microphone(
                seconds=batch_seconds, chunk_size=self.chunk_size
            )
