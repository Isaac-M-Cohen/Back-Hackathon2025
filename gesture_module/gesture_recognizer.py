"""Realtime gesture recognition loop that emits events to the controller.

Uses the gesture ML pipeline from video_module (MediaPipe landmarks only),
applies temporal smoothing, and forwards recognized labels to CommandController.
"""

from __future__ import annotations

import threading
from typing import Optional

import cv2
import mediapipe as mp

from command_controller.controller import CommandController
from utils.file_utils import load_json
from video_module import (
    GestureDataset,
    GestureRecognizer as MLRecognizer,
    normalize_landmarks,
    VideoStream,
)


class RealTimeGestureRecognizer:
    def __init__(
        self,
        controller: CommandController,
        *,
        user_id: str = "default",
        config_path: str = "config/gesture_config.json",
        confidence_threshold: float = 0.6,
        stable_frames: int = 5,
        show_window: bool = False,
    ) -> None:
        self.controller = controller
        self.show_window = show_window
        self._thread: Optional[threading.Thread] = None
        self._window_name = "Gesture Recognition"
        cfg = load_json(config_path)

        dataset = GestureDataset(user_id=user_id)
        artifacts = dataset.load_model()
        if artifacts is None:
            # Build a fallback NONE-only model so recognition can start without training.
            artifacts = dataset.build_none_only_artifacts(window_size=int(cfg.get("window_size", 30)))

        input_dim = getattr(artifacts.model, "feature_dim", None)
        if input_dim is None and hasattr(artifacts.model, "coefs_"):
            input_dim = artifacts.model.coefs_[0].shape[0]
        self.window_size = input_dim // 63 if input_dim and input_dim % 63 == 0 else int(cfg.get("window_size", 30))
        self.recognizer = MLRecognizer(
            artifacts,
            window_size=self.window_size,
            confidence_threshold=confidence_threshold,
            stable_frames=stable_frames,
        )

        detection_conf = float(cfg.get("detection_threshold", 0.6))
        tracking_conf = float(cfg.get("min_tracking_confidence", cfg.get("tracking_threshold", 0.6)))
        device_index = int(cfg.get("device_index", 0))

        self.stream = VideoStream(device_index=device_index)
        self._hands = mp.solutions.hands.Hands(
            static_image_mode=False,
            max_num_hands=1,
            min_detection_confidence=detection_conf,
            min_tracking_confidence=tracking_conf,
            model_complexity=1,
        )
        self._drawer = mp.solutions.drawing_utils
        self.active = False

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            print("[GESTURE] Recognizer already running (background)")
            return
        if self.active:
            print("[GESTURE] Recognizer already running")
            return

        def _runner() -> None:
            try:
                self._run_loop()
            except Exception as exc:  # pragma: no cover
                print(f"[GESTURE] Recognizer error: {exc}")
            finally:
                self.active = False
                self._thread = None

        self._thread = threading.Thread(target=_runner, name="GestureRecognizer", daemon=False)
        self._thread.start()

    def start_blocking(self) -> None:
        if self.active:
            print("[GESTURE] Recognizer already running")
            return
        self._run_loop()

    def _run_loop(self) -> None:
        self.stream.open()
        self.active = True
        print("[GESTURE] Recognition started — press 'q' to exit.")
        try:
            while self.active:
                ok, frame = self.stream.read()
                if not ok or frame is None:
                    print("[GESTURE] Failed to read from camera.")
                    break

                results = self._hands.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))

                label = "NONE"
                confidence = 0.0
                if results.multi_hand_landmarks:
                    hand_landmarks = results.multi_hand_landmarks[0]
                    handedness = None
                    if results.multi_handedness:
                        handedness = results.multi_handedness[0].classification[0].label
                    features = normalize_landmarks(
                        hand_landmarks.landmark,
                        handedness=handedness,
                        mirror_left=True,
                    )
                    label, confidence = self.recognizer.observe(features)

                    self._drawer.draw_landmarks(
                        frame,
                        hand_landmarks,
                        mp.solutions.hands.HAND_CONNECTIONS,
                    )
                else:
                    label, confidence = self.recognizer.observe(None)

                if label != "NONE":
                    self.controller.handle_event(
                        source="gesture", action=label, payload={"confidence": confidence}
                    )

                if self.show_window:
                    cv2.putText(
                        frame,
                        f"{label} ({confidence:.2f})",
                        (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.8,
                        (0, 255, 0) if label != "NONE" else (128, 128, 128),
                        2,
                    )
                    cv2.imshow(self._window_name, frame)
                    if (cv2.waitKey(1) & 0xFF) == ord("q"):
                        break
        except cv2.error as exc:
            print(f"[GESTURE] OpenCV error: {exc}")
        finally:
            self.stop()

    def stop(self) -> None:
        self.active = False
        self.stream.close()
        self._hands.close()
        cv2.destroyAllWindows()
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None
        print("[GESTURE] Recognition stopped")

    def is_running(self) -> bool:
        return bool((self._thread and self._thread.is_alive()) or self.active)
