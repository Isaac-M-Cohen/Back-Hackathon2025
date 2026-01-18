"""High-level helpers to collect gestures, train, and start recognition on demand.

This keeps the camera closed until explicitly invoked by the UI/consumer.
"""

from __future__ import annotations

from command_controller.controller import CommandController
from utils.log_utils import tprint
from video_module.gesture_ml import GestureCollector, GestureDataset
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gesture_module.gesture_recognizer import RealTimeGestureRecognizer


class GestureWorkflow:
    """Wraps dataset, training, and realtime recognition for a user."""

    def __init__(self, user_id: str = "default", window_size: int = 30) -> None:
        self.user_id = user_id
        self.window_size = window_size
        self.dataset = GestureDataset(user_id=user_id)
        self._recognizer: "RealTimeGestureRecognizer" | None = None
        self._last_detection: dict | None = None
        self.ensure_presets_loaded()

    def ensure_presets_loaded(self) -> bool:
        """Ensure preset keypoint CSV/labels exist under user_data."""
        return self.dataset.ensure_presets()

    def collect_static(self, label: str, target_frames: int = 60, *, show_preview: bool = False) -> None:
        collector = GestureCollector(show_preview=show_preview)
        collector.collect_static(self.dataset, label, target_frames=target_frames)

    def collect_dynamic(
        self,
        label: str,
        *,
        repetitions: int = 5,
        sequence_length: int = 30,
        show_preview: bool = False,
    ) -> None:
        collector = GestureCollector(show_preview=show_preview)
        collector.collect_dynamic(
            self.dataset,
            label,
            repetitions=repetitions,
            show_preview=show_preview,
        )

    def train_and_save(self) -> None:
        raise RuntimeError(
            "Training is handled via the TFLite notebooks. Run the training notebooks to update models."
        )

    def start_recognition(
        self,
        controller: CommandController,
        *,
        confidence_threshold: float = 0.6,
        stable_frames: int = 5,
        emit_cooldown_secs: float = 0.5,
        show_window: bool = True,
        emit_actions: bool = True,
        max_fps: float = 0.0,
        watchdog_timeout_secs: float = 0.0,
    ) -> None:
        """Open the camera and start realtime recognition."""
        from gesture_module.gesture_recognizer import RealTimeGestureRecognizer

        if self._recognizer and self._recognizer.is_running():
            tprint("[GESTURE] Recognizer already running")
            return
        self._recognizer = RealTimeGestureRecognizer(
            controller,
            user_id=self.user_id,
            confidence_threshold=confidence_threshold,
            stable_frames=stable_frames,
            show_window=show_window,
            on_detection=self._record_detection,
            emit_cooldown_secs=emit_cooldown_secs,
            enabled_labels=set(self.dataset.enabled),
            emit_actions=emit_actions,
            max_fps=max_fps,
            watchdog_timeout_secs=watchdog_timeout_secs,
        )
        self._recognizer.start()

    def stop_recognition(self) -> None:
        if self._recognizer:
            try:
                self._recognizer.stop()
            finally:
                self._recognizer = None

    def is_recognizing(self) -> bool:
        return bool(self._recognizer and self._recognizer.is_running())

    def refresh_enabled_labels(self) -> None:
        if self._recognizer:
            self._recognizer.set_enabled_labels(set(self.dataset.enabled))

    def apply_runtime_settings(self, settings: dict) -> None:
        if not self._recognizer:
            return
        emit_cooldown_ms = int(settings.get("recognition_emit_cooldown_ms", 500))
        emit_cooldown_secs = max(0.0, emit_cooldown_ms / 1000.0)
        stable_frames = int(settings.get("recognition_stable_frames", 5))
        max_fps_value = settings.get("recognition_max_fps", 0)
        max_fps = float(max_fps_value) if max_fps_value is not None else 0.0
        watchdog_ms = settings.get("recognition_watchdog_timeout_ms", 0)
        watchdog_secs = float(watchdog_ms) / 1000.0 if watchdog_ms else 0.0
        confidence_threshold = float(settings.get("recognition_confidence_threshold", 0.6))
        emit_actions = bool(settings.get("enable_commands", True))
        self._recognizer.apply_runtime_settings(
            confidence_threshold=confidence_threshold,
            stable_frames=stable_frames,
            emit_cooldown_secs=emit_cooldown_secs,
            emit_actions=emit_actions,
            max_fps=max_fps,
            watchdog_timeout_secs=watchdog_secs,
        )

    def _record_detection(self, *, label: str, confidence: float) -> None:
        self._last_detection = {
            "label": label,
            "confidence": confidence,
        }

    def last_detection(self) -> dict | None:
        return self._last_detection
