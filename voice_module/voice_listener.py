"""Listens for audio input and forwards recognized commands via local Whisper.

WAV-based pipeline: records to in-memory WAV, detects silence, normalizes audio,
then transcribes locally using faster-whisper.
"""
import asyncio
import audioop
import io
import threading
import time
import wave
from typing import Callable, Optional

from command_controller.controller import CommandController
from utils.log_utils import tprint
from utils.file_utils import load_json
from utils.settings_store import get_settings, is_deep_logging
from voice_module.stt_engine import SpeechToTextEngine


class VoiceListener:
    """WAV-based voice listener with silence detection and audio normalization."""

    def __init__(
        self,
        controller: CommandController,
        listen_seconds: float | None = None,
        chunk_size: int = 4096,
        single_batch: bool = False,
        log_token_usage: bool = False,
        *,
        on_partial_transcript: Optional[Callable[[str], None]] = None,
        on_final_transcript: Optional[Callable[[str], None]] = None,
        on_audio_level: Optional[Callable[[float], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
        on_state: Optional[Callable[[str], None]] = None,
        send_to_executor: bool = False,
        # Silence detection parameters
        silence_threshold: float = 0.02,
        silence_duration_secs: float = 1.1,
        min_record_duration_secs: float = 0.7,
        max_record_duration_secs: float = 8.0,
        min_voice_duration_secs: float = 0.12,
        pre_roll_secs: float = 0.25,
        min_gap_secs: float = 0.25,
        # Legacy compatibility parameters (mapped to new ones)
        pause_threshold_secs: float | None = None,
        live_transcribe_interval_secs: float | None = None,
        min_command_seconds: float | None = None,
        audio_level_threshold: float | None = None,
        partial_window_secs: float | None = None,
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
        self.on_error = on_error
        self.on_state = on_state
        self.send_to_executor = send_to_executor

        # Silence detection settings (use legacy names if provided for backwards compat)
        self.silence_threshold = audio_level_threshold if audio_level_threshold is not None else silence_threshold
        self.silence_duration_secs = pause_threshold_secs if pause_threshold_secs is not None else silence_duration_secs
        self.min_record_duration_secs = min_command_seconds if min_command_seconds is not None else min_record_duration_secs
        self.max_record_duration_secs = max(0.5, max_record_duration_secs)
        self.min_voice_duration_secs = max(0.0, min_voice_duration_secs)
        self.pre_roll_secs = max(0.0, pre_roll_secs)
        self.min_gap_secs = max(0.0, min_gap_secs)

        # Ensure valid ranges
        self.silence_threshold = max(0.0, self.silence_threshold)
        self.silence_duration_secs = max(0.1, self.silence_duration_secs)
        self.min_record_duration_secs = max(0.1, self.min_record_duration_secs)

        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._single_batch_done = False
        self._transcribing = False
        self._last_record_end_time: float | None = None
        self._log_debug = False
        self._refresh_log_flags()

    def start(self) -> None:
        """Begin microphone capture in a background thread."""
        if self._thread and self._thread.is_alive():
            tprint("[VOICE] Listener already running")
            return
        self._refresh_log_flags()
        self._stop_event.clear()
        self._single_batch_done = False

        def _runner() -> None:
            try:
                if self.single_batch:
                    asyncio.run(self._record_and_transcribe_once())
                else:
                    asyncio.run(self._continuous_wav_loop())
            except Exception as exc:  # pragma: no cover - surface runtime issues
                tprint(f"[VOICE] Listener error: {exc}")
                if self.on_error:
                    self.on_error(str(exc))
            finally:
                self._single_batch_done = True
                self._stop_event.set()
                self._thread = None

        tprint("[VOICE] Listener starting (WAV pipeline -> local Whisper)...")
        self._thread = threading.Thread(
            target=_runner, name="VoiceListenerWAV", daemon=False
        )
        self._thread.start()

    def stop(self) -> None:
        """Signal the listener to stop after the current recording."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None

    def is_running(self) -> bool:
        if self.single_batch and self._single_batch_done:
            return False
        return bool(self._thread and self._thread.is_alive())

    async def _continuous_wav_loop(self) -> None:
        """Continuously record WAV segments, detect silence, and transcribe."""
        queue: asyncio.Queue[tuple[bytes, int, float] | None] = asyncio.Queue(maxsize=2)
        worker = asyncio.create_task(self._transcribe_worker(queue))
        try:
            while not self._stop_event.is_set():
                try:
                    audio_data, sample_rate, duration = await self._record_with_silence_detection()
                    if self._stop_event.is_set():
                        break
                    if not audio_data or duration < self.min_record_duration_secs:
                        if self._log_debug and duration > 0:
                            tprint(f"[VOICE] Recording too short ({duration:.2f}s), skipping")
                        continue
                    try:
                        queue.put_nowait((audio_data, sample_rate, duration))
                    except asyncio.QueueFull:
                        if self._log_debug:
                            tprint("[VOICE] Transcription backlog; dropping segment")
                except Exception as exc:
                    if self.on_error:
                        self.on_error(str(exc))
                    tprint(f"[VOICE] Recording error: {exc}")
                    await asyncio.sleep(0.2)
        finally:
            await queue.put(None)
            await worker

    async def _record_and_transcribe_once(self) -> None:
        """Record audio until silence, normalize, transcribe, and dispatch."""
        if self.on_state:
            self.on_state("listening")

        # Record audio with silence detection
        audio_data, sample_rate, duration = await self._record_with_silence_detection()

        if not audio_data or duration < self.min_record_duration_secs:
            if self._log_debug:
                tprint(f"[VOICE] Recording too short ({duration:.2f}s), skipping")
            return

        if self._stop_event.is_set():
            return

        await self._transcribe_segment(audio_data, sample_rate)

    async def _record_with_silence_detection(self) -> tuple[bytes, int, float]:
        """Record microphone audio until silence is detected.

        Returns:
            Tuple of (audio_bytes, sample_rate, duration_seconds)
        """
        import pyaudio

        pa = pyaudio.PyAudio()
        sample_rate = self.stt.default_sample_rate
        input_device_index = self._resolve_microphone_device_index()

        stream = pa.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=sample_rate,
            input=True,
            frames_per_buffer=self.chunk_size,
            input_device_index=input_device_index,
        )

        audio_chunks: list[bytes] = []
        pre_roll: list[bytes] = []
        recording_started = False
        recording_start_time: float | None = None
        last_voice_time: float | None = None
        voice_active_start: float | None = None
        bytes_per_sample = 2  # 16-bit audio
        pre_roll_frames = max(0, int((self.pre_roll_secs * sample_rate) / self.chunk_size))

        try:
            if self._last_record_end_time:
                gap = time.monotonic() - self._last_record_end_time
                if gap < self.min_gap_secs:
                    await asyncio.sleep(self.min_gap_secs - gap)

            while not self._stop_event.is_set():
                data = await asyncio.to_thread(
                    stream.read, self.chunk_size, exception_on_overflow=False
                )
                if not data:
                    continue

                # Compute audio level
                level = self._compute_audio_level(data)
                if self.on_audio_level:
                    self.on_audio_level(level)

                now = time.monotonic()

                # Detect voice activity with a short debounce
                if level >= self.silence_threshold:
                    last_voice_time = now
                    if voice_active_start is None:
                        voice_active_start = now
                    if not recording_started and (now - voice_active_start) >= self.min_voice_duration_secs:
                        recording_started = True
                        recording_start_time = now
                        if pre_roll:
                            audio_chunks.extend(pre_roll)
                            pre_roll.clear()
                        if self.on_state:
                            self.on_state("recording")
                        if self._log_debug:
                            tprint("[VOICE] Voice detected, recording started")
                else:
                    voice_active_start = None

                # Only buffer audio once recording has started
                if recording_started:
                    audio_chunks.append(data)

                    # Check for silence timeout
                    if last_voice_time is not None:
                        silence_elapsed = now - last_voice_time
                        if silence_elapsed >= self.silence_duration_secs:
                            if self._log_debug:
                                tprint(f"[VOICE] Silence detected ({silence_elapsed:.2f}s)")
                            break
                    # Enforce maximum record duration to avoid long stalls
                    if recording_start_time is not None:
                        elapsed = now - recording_start_time
                        if elapsed >= self.max_record_duration_secs:
                            if self._log_debug:
                                tprint(f"[VOICE] Max record duration reached ({elapsed:.2f}s)")
                            break

                if not recording_started and pre_roll_frames > 0:
                    pre_roll.append(data)
                    if len(pre_roll) > pre_roll_frames:
                        pre_roll.pop(0)

        finally:
            stream.stop_stream()
            stream.close()
            pa.terminate()

        # Calculate duration
        if not audio_chunks or not recording_start_time:
            return b"", sample_rate, 0.0

        audio_bytes = b"".join(audio_chunks)
        duration = len(audio_bytes) / (sample_rate * bytes_per_sample)
        self._last_record_end_time = time.monotonic()
        return audio_bytes, sample_rate, duration

    async def _transcribe_worker(
        self, queue: asyncio.Queue[tuple[bytes, int, float] | None]
    ) -> None:
        while True:
            item = await queue.get()
            if item is None:
                return
            audio_data, sample_rate, _duration = item
            await self._transcribe_segment(audio_data, sample_rate)

    async def _transcribe_segment(self, audio_data: bytes, sample_rate: int) -> None:
        """Normalize, transcribe, and dispatch a recorded audio segment."""
        if self._stop_event.is_set():
            return
        if self.on_state:
            self.on_state("transcribing")

        normalized_audio = self._normalize_audio(audio_data)
        wav_buffer = self._create_wav_buffer(normalized_audio, sample_rate)

        self._transcribing = True
        try:
            text = await self.stt.transcribe_wav_bytes(wav_buffer.getvalue())
            text = text.strip()

            if self._log_debug:
                tprint(f"[VOICE] Transcript: {text!r}")

            if text:
                tprint(f"[VOICE] Transcript: {text}")
                if self.log_token_usage:
                    usage = self.stt.format_usage()
                    if usage:
                        tprint(f"[VOICE] Token usage: {usage}")
                if self.on_final_transcript:
                    self.on_final_transcript(text)
                if self.send_to_executor:
                    self.controller.handle_event(source="voice", action=text)
        finally:
            self._transcribing = False

        if self.on_state:
            self.on_state("listening")

    def _compute_audio_level(self, pcm_bytes: bytes) -> float:
        """Compute normalized audio level from PCM16 bytes."""
        if not pcm_bytes:
            return 0.0
        rms = audioop.rms(pcm_bytes, 2)
        return min(1.0, rms / 32768.0)

    def _normalize_audio(self, audio_bytes: bytes, target_level: float = 0.8) -> bytes:
        """Normalize audio amplitude to target level.

        Args:
            audio_bytes: Raw PCM16 audio bytes
            target_level: Target RMS level (0.0 to 1.0), default 0.8

        Returns:
            Normalized PCM16 audio bytes
        """
        if not audio_bytes:
            return audio_bytes

        # Get current max amplitude
        max_amp = audioop.max(audio_bytes, 2)
        if max_amp == 0:
            return audio_bytes

        # Calculate gain factor to reach target level
        # Target is relative to max possible amplitude (32767)
        target_amp = int(32767 * target_level)
        gain_factor = target_amp / max_amp

        # Clamp gain to prevent over-amplification of quiet audio
        gain_factor = min(gain_factor, 10.0)

        if gain_factor <= 1.0:
            # Audio is already loud enough
            return audio_bytes

        # Apply gain using audioop.mul
        try:
            normalized = audioop.mul(audio_bytes, 2, gain_factor)
            return normalized
        except audioop.error:
            return audio_bytes

    def _create_wav_buffer(self, audio_bytes: bytes, sample_rate: int) -> io.BytesIO:
        """Create an in-memory WAV file from PCM16 audio bytes."""
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(audio_bytes)
        wav_buffer.seek(0)
        return wav_buffer

    def _resolve_microphone_device_index(self) -> int | None:
        """Get configured microphone device index from settings."""
        settings = load_json("config/app_settings.json")
        value = settings.get("microphone_device_index")
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _refresh_log_flags(self) -> None:
        """Refresh debug logging flags from settings."""
        try:
            settings = get_settings()
        except Exception:
            settings = {}
        self._log_debug = bool(settings.get("log_command_debug")) or is_deep_logging()
