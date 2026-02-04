"""Listens for audio input and forwards recognized commands via local Whisper."""
import asyncio
import audioop
import threading
import time
from typing import AsyncIterable, Callable, Optional

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
        *,
        on_partial_transcript: Optional[Callable[[str], None]] = None,
        on_final_transcript: Optional[Callable[[str], None]] = None,
        on_audio_level: Optional[Callable[[float], None]] = None,
        pause_threshold_secs: float = 1.2,
        live_transcribe_interval_secs: float = 1.2,
        min_command_seconds: float = 0.6,
        audio_level_threshold: float = 0.02,
        partial_window_secs: float = 8.0,
    ) -> None:
        self.controller = controller
        self.stt = SpeechToTextEngine()
        self.listen_seconds = listen_seconds
        self.chunk_size = chunk_size
        self.single_batch = single_batch
        self.log_token_usage = log_token_usage
        self.on_partial_transcript = on_partial_transcript
        self.on_final_transcript = on_final_transcript
        self.on_audio_level = on_audio_level
        self.pause_threshold_secs = max(0.1, pause_threshold_secs)
        self.live_transcribe_interval_secs = max(0.5, live_transcribe_interval_secs)
        self.min_command_seconds = max(0.1, min_command_seconds)
        self.audio_level_threshold = max(0.0, audio_level_threshold)
        self.partial_window_secs = max(1.0, partial_window_secs)
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._single_batch_done = False
        self._transcribing = False

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

        tprint("[VOICE] Listener starting (mic -> local Whisper)...")
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
        """Consume an audio stream and forward transcripts."""
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
    ) -> AsyncIterable[bytes]:
        """Capture microphone audio with PyAudio and yield raw PCM16 chunks."""
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
                yield data
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
        transcription = transcription.strip()
        tprint(f"[VOICE] Transcript: {transcription}")
        if self.log_token_usage:
            usage = self.stt.format_usage()
            if usage:
                tprint(f"[VOICE] Token usage: {usage}")
        if transcription:
            self.controller.handle_event(source="voice", action=transcription)

    async def _continuous_loop(self) -> None:
        """Continuously capture mic audio, emit live transcripts, and send final commands."""
        await self._stream_with_pause_detection()

    async def _stream_with_pause_detection(self) -> None:
        audio_stream = self.microphone_stream(seconds=0, chunk_size=self.chunk_size)
        audio_buffer = bytearray()
        last_voice_ts: float | None = None
        last_partial_ts: float = 0.0
        utterance_start_ts: float | None = None
        max_partial_bytes = int(self.partial_window_secs * self.stt.default_sample_rate * 2)

        async for chunk in audio_stream:
            if self._stop_event.is_set():
                break
            if not chunk:
                await asyncio.sleep(0)
                continue

            level = self._compute_audio_level(chunk)
            if self.on_audio_level:
                self.on_audio_level(level)

            now = time.monotonic()
            if level >= self.audio_level_threshold:
                last_voice_ts = now
                if utterance_start_ts is None:
                    utterance_start_ts = now

            audio_buffer.extend(chunk)

            if (
                utterance_start_ts is not None
                and now - last_partial_ts >= self.live_transcribe_interval_secs
            ):
                snapshot = bytes(audio_buffer[-max_partial_bytes:])
                await self._emit_partial_transcript(snapshot)
                last_partial_ts = now

            if (
                utterance_start_ts is not None
                and last_voice_ts is not None
                and now - last_voice_ts >= self.pause_threshold_secs
            ):
                duration = now - utterance_start_ts
                if duration >= self.min_command_seconds:
                    await self._emit_final_transcript(bytes(audio_buffer))
                audio_buffer.clear()
                utterance_start_ts = None
                last_voice_ts = None
                last_partial_ts = now

        # Flush any buffered audio on stop.
        if audio_buffer:
            await self._emit_final_transcript(bytes(audio_buffer))

    def _compute_audio_level(self, pcm_bytes: bytes) -> float:
        if not pcm_bytes:
            return 0.0
        rms = audioop.rms(pcm_bytes, 2)
        return min(1.0, rms / 32768.0)

    async def _emit_partial_transcript(self, audio_bytes: bytes) -> None:
        if self._transcribing or not audio_bytes:
            return
        self._transcribing = True
        try:
            text = (await self.stt.transcribe_audio_bytes(audio_bytes)).strip()
            if text and self.on_partial_transcript:
                self.on_partial_transcript(text)
        finally:
            self._transcribing = False

    async def _emit_final_transcript(self, audio_bytes: bytes) -> None:
        if not audio_bytes:
            return
        while self._transcribing:
            await asyncio.sleep(0.05)
        self._transcribing = True
        try:
            text = (await self.stt.transcribe_audio_bytes(audio_bytes)).strip()
            if not text:
                return
            tprint(f"[VOICE] Transcript: {text}")
            if self.log_token_usage:
                usage = self.stt.format_usage()
                if usage:
                    tprint(f"[VOICE] Token usage: {usage}")
            if self.on_final_transcript:
                self.on_final_transcript(text)
            self.controller.handle_event(source="voice", action=text)
        finally:
            self._transcribing = False
