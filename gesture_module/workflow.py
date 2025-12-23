"""High-level helpers to collect gestures, train, and start recognition on demand.

This keeps the camera closed until explicitly invoked by the UI/consumer.
"""

from __future__ import annotations

from command_controller.controller import CommandController
from video_module import (
    GestureCollector,
    GestureDataset,
    GestureTrainer,
    VideoStream,
)
from gesture_module.gesture_recognizer import RealTimeGestureRecognizer


class GestureWorkflow:
    """Wraps dataset, training, and realtime recognition for a user."""

    def __init__(self, user_id: str = "default", window_size: int = 30) -> None:
        self.user_id = user_id
        self.window_size = window_size
        self.dataset = GestureDataset(user_id=user_id)
        self.trainer = GestureTrainer(window_size=window_size)
        self._recognizer: RealTimeGestureRecognizer | None = None

    def collect_static(self, label: str, target_frames: int = 60, *, show_preview: bool = False) -> None:
        collector = GestureCollector(window_size=self.window_size, show_preview=show_preview)
        samples = collector.collect_static(label, target_frames=target_frames)
        if samples:
            self.dataset.add_samples(label, samples)
            self.dataset.save()

    def collect_dynamic(
        self,
        label: str,
        *,
        repetitions: int = 5,
        sequence_length: int = 30,
        show_preview: bool = False,
    ) -> None:
        collector = GestureCollector(window_size=self.window_size, show_preview=show_preview)
        samples = collector.collect_dynamic(
            label, repetitions=repetitions, sequence_length=sequence_length
        )
        if samples:
            self.dataset.add_samples(label, samples)
            self.dataset.save()

    def train_and_save(self) -> None:
        artifacts = self.trainer.train(self.dataset)
        self.dataset.save_model(artifacts)

    def start_recognition(
        self,
        controller: CommandController,
        *,
        confidence_threshold: float = 0.6,
        stable_frames: int = 5,
        show_window: bool = True,
    ) -> None:
        """Open the camera and start realtime recognition."""
        if self._recognizer and self._recognizer.is_running():
            print("[GESTURE] Recognizer already running")
            return
        self._recognizer = RealTimeGestureRecognizer(
            controller,
            user_id=self.user_id,
            confidence_threshold=confidence_threshold,
            stable_frames=stable_frames,
            show_window=show_window,
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
