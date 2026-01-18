"""Realtime gesture recognition loop using MediaPipe + TFLite classifiers."""

from __future__ import annotations

import threading
import time
from collections import Counter, deque
from typing import Optional
from command_controller.controller import CommandController
from utils.file_utils import load_json
from utils.log_utils import tprint
from utils.settings_store import deep_log, is_deep_logging
from video_module.gesture_ml import GestureDataset
from video_module.tflite_classifiers import KeyPointClassifier, PointHistoryClassifier
from video_module.tflite_pipeline import (
    POINT_HISTORY_LEN,
    PointHistoryBuffer,
    calc_landmark_list,
    pre_process_landmark,
    pre_process_point_history,
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
        on_detection: Optional[callable] = None,
        emit_cooldown_secs: float = 0.5,
        enabled_labels: Optional[set[str]] = None,
        emit_actions: bool = True,
        max_fps: float = 0.0,
        watchdog_timeout_secs: float = 0.0,
    ) -> None:
        self.controller = controller
        self.show_window = show_window
        self.on_detection = on_detection
        self.emit_cooldown_secs = emit_cooldown_secs
        self.enabled_labels = enabled_labels
        self.emit_actions = emit_actions
        self.max_fps = max_fps
        self.watchdog_timeout_secs = watchdog_timeout_secs
        self.confidence_threshold = confidence_threshold
        self._thread: Optional[threading.Thread] = None
        self._window_name = "Gesture Recognition"
        cfg = load_json(config_path)

        dataset = GestureDataset(user_id=user_id)
        dataset.ensure_presets()
        self._keypoint_labels = dataset.keypoint_labels()
        self._point_history_labels = dataset.point_history_labels()
        self._pointer_id = (
            self._keypoint_labels.index("Pointer")
            if "Pointer" in self._keypoint_labels
            else 2
        )
        self._keypoint_history = deque(maxlen=stable_frames)
        self._point_history = PointHistoryBuffer(maxlen=POINT_HISTORY_LEN)
        self._finger_gesture_history = deque(maxlen=POINT_HISTORY_LEN)

        self._keypoint_classifier = None
        if dataset.keypoint_model_path.exists():
            try:
                self._keypoint_classifier = KeyPointClassifier(dataset.keypoint_model_path)
            except Exception as exc:
                tprint(f"[GESTURE] Failed to load keypoint model: {exc}")
        elif is_deep_logging():
            deep_log(f"[DEEP][GESTURE] Missing keypoint model at {dataset.keypoint_model_path}")

        self._point_history_classifier = None
        if dataset.point_history_model_path.exists():
            try:
                self._point_history_classifier = PointHistoryClassifier(
                    dataset.point_history_model_path
                )
            except Exception as exc:
                tprint(f"[GESTURE] Failed to load point history model: {exc}")
        elif is_deep_logging():
            deep_log(f"[DEEP][GESTURE] Missing point history model at {dataset.point_history_model_path}")

        detection_conf = float(cfg.get("detection_threshold", 0.6))
        tracking_conf = float(cfg.get("min_tracking_confidence", cfg.get("tracking_threshold", 0.6)))
        device_index = int(cfg.get("device_index", 0))

        try:
            import mediapipe as mp
        except ImportError as exc:
            raise RuntimeError(
                "MediaPipe is required for recognition. Install mediapipe>=0.10."
            ) from exc
        try:
            import cv2
        except ImportError as exc:
            raise RuntimeError(
                "OpenCV is required for recognition. Install opencv-python."
            ) from exc
        mp_solutions = getattr(mp, "solutions", None)
        if mp_solutions is None:
            raise RuntimeError(
                "MediaPipe is missing 'solutions'. Install mediapipe>=0.10 in the active interpreter."
            )

        from video_module.video_stream import VideoStream

        self._cv2 = cv2
        self.stream = VideoStream(device_index=device_index)
        self._hands = mp_solutions.hands.Hands(
            static_image_mode=False,
            max_num_hands=1,
            min_detection_confidence=detection_conf,
            min_tracking_confidence=tracking_conf,
            model_complexity=1,
        )
        self._drawer = mp_solutions.drawing_utils
        self._hand_connections = mp_solutions.hands.HAND_CONNECTIONS
        self.active = False
        self._stop_event = threading.Event()
        self._closed = False
        self._last_emitted_label: str | None = None
        self._last_emit_time: float = 0.0
        self._last_frame_ts: float = 0.0
        deep_log(
            "[DEEP][GESTURE] init "
            f"labels={len(self._keypoint_labels)} "
            f"point_history_labels={len(self._point_history_labels)} "
            f"enabled={len(self.enabled_labels or set())} "
            f"threshold={self.confidence_threshold:.2f} "
            f"stable_frames={stable_frames} "
            f"cooldown={emit_cooldown_secs:.2f}s "
            f"max_fps={self.max_fps:.1f} "
            f"watchdog={self.watchdog_timeout_secs:.2f}s"
        )

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            tprint("[GESTURE] Recognizer already running (background)")
            return
        if self.active:
            tprint("[GESTURE] Recognizer already running")
            return
        self._stop_event.clear()

        def _runner() -> None:
            try:
                self._run_loop()
            except Exception as exc:  # pragma: no cover
                tprint(f"[GESTURE] Recognizer error: {exc}")
            finally:
                self._cleanup(join_thread=False)

        self._thread = threading.Thread(target=_runner, name="GestureRecognizer", daemon=False)
        self._thread.start()

    def start_blocking(self) -> None:
        if self.active:
            tprint("[GESTURE] Recognizer already running")
            return
        self._run_loop()

    def _run_loop(self) -> None:
        self.stream.open()
        self.active = True
        self._last_frame_ts = time.monotonic()
        if is_deep_logging() and not self.enabled_labels:
            deep_log("[DEEP][GESTURE] enabled_labels empty; all detections will be NONE")
        tprint("[GESTURE] Recognition started — press 'q' to exit.")
        try:
            while self.active and not self._stop_event.is_set():
                if self.watchdog_timeout_secs > 0:
                    stalled_for = time.monotonic() - self._last_frame_ts
                    if stalled_for > self.watchdog_timeout_secs:
                        tprint("[GESTURE] Watchdog triggered; stopping recognition.")
                        break
                loop_start = time.monotonic()
                ok, frame = self.stream.read()
                if not ok or frame is None:
                    tprint("[GESTURE] Failed to read from camera.")
                    break
                self._last_frame_ts = time.monotonic()

                frame = self._cv2.flip(frame, 1)
                results = self._hands.process(
                    self._cv2.cvtColor(frame, self._cv2.COLOR_BGR2RGB)
                )

                label = "NONE"
                confidence = 0.0
                if results.multi_hand_landmarks:
                    hand_landmarks = results.multi_hand_landmarks[0]
                    landmark_list = calc_landmark_list(frame, hand_landmarks)
                    pre_processed_landmark_list = pre_process_landmark(landmark_list)
                    keypoint_id = -1
                    keypoint_score = 0.0
                    if self._keypoint_classifier:
                        keypoint_id, keypoint_score = self._keypoint_classifier(
                            pre_processed_landmark_list
                        )
                    if keypoint_id == self._pointer_id:
                        self._point_history.append(landmark_list[8])
                    else:
                        self._point_history.zeros()

                    point_history_list = pre_process_point_history(
                        frame, self._point_history.as_list()
                    )
                    finger_gesture_id = 0
                    finger_gesture_score = 0.0
                    if (
                        self._point_history_classifier
                        and len(point_history_list) == (POINT_HISTORY_LEN * 2)
                    ):
                        finger_gesture_id, finger_gesture_score = self._point_history_classifier(
                            point_history_list
                        )
                    self._finger_gesture_history.append(finger_gesture_id)
                    most_common_fg = Counter(self._finger_gesture_history).most_common(1)
                    if most_common_fg:
                        finger_gesture_id = most_common_fg[0][0]

                    self._keypoint_history.append(keypoint_id)
                    most_common_keypoint = Counter(self._keypoint_history).most_common(1)
                    if most_common_keypoint:
                        keypoint_id = most_common_keypoint[0][0]

                    label, confidence = self._resolve_label(
                        keypoint_id=keypoint_id,
                        keypoint_score=keypoint_score,
                        finger_gesture_id=finger_gesture_id,
                        finger_gesture_score=finger_gesture_score,
                    )

                    self._drawer.draw_landmarks(
                        frame,
                        hand_landmarks,
                        self._hand_connections,
                    )
                else:
                    self._point_history.zeros()
                    label, confidence = "NONE", 0.0

                emit_label = label if self._is_enabled(label) else "NONE"

                if emit_label != "NONE":
                    now = time.monotonic()
                    in_cooldown = (now - self._last_emit_time) < self.emit_cooldown_secs
                    if (emit_label != self._last_emitted_label) and not in_cooldown:
                        if is_deep_logging():
                            deep_log(
                                "[DEEP][GESTURE] emit "
                                f"label={emit_label} confidence={confidence:.3f} "
                                f"cooldown={self.emit_cooldown_secs:.2f}s"
                            )
                        if self.emit_actions:
                            self.controller.handle_event(
                                source="gesture", action=emit_label, payload={"confidence": confidence}
                            )
                        self._last_emitted_label = emit_label
                        self._last_emit_time = now
                if emit_label == "NONE":
                    self._last_emitted_label = None
                    self._last_emit_time = 0.0
                if self.on_detection:
                    try:
                        # Report only enabled labels (or NONE) for UI status.
                        self.on_detection(label=emit_label, confidence=confidence)
                    except Exception:
                        pass

                if self.show_window:
                    self._cv2.putText(
                        frame,
                        f"{label} ({confidence:.2f})",
                        (10, 30),
                        self._cv2.FONT_HERSHEY_SIMPLEX,
                        0.8,
                        (0, 255, 0) if label != "NONE" else (128, 128, 128),
                        2,
                    )
                    self._cv2.imshow(self._window_name, frame)
                    if (self._cv2.waitKey(1) & 0xFF) == ord("q"):
                        break
                self._sleep_for_fps(loop_start)
        except Exception as exc:
            tprint(f"[GESTURE] OpenCV error: {exc}")
        finally:
            self._cleanup(join_thread=False)

    def _sleep_for_fps(self, loop_start: float) -> None:
        if not self.max_fps or self.max_fps <= 0:
            return
        elapsed = time.monotonic() - loop_start
        target = 1.0 / self.max_fps
        remaining = target - elapsed
        if remaining > 0:
            time.sleep(remaining)

    def _resolve_label(
        self,
        *,
        keypoint_id: int,
        keypoint_score: float,
        finger_gesture_id: int,
        finger_gesture_score: float,
    ) -> tuple[str, float]:
        if finger_gesture_id and self._point_history_labels:
            if 0 <= finger_gesture_id < len(self._point_history_labels):
                return self._point_history_labels[finger_gesture_id], finger_gesture_score
        if self._keypoint_labels and 0 <= keypoint_id < len(self._keypoint_labels):
            if keypoint_score >= self.confidence_threshold:
                return self._keypoint_labels[keypoint_id], keypoint_score
        return "NONE", 0.0

    def stop(self) -> None:
        self.active = False
        self._stop_event.set()
        if self._thread and self._thread.is_alive() and threading.current_thread() is not self._thread:
            self._thread.join(timeout=5)
        if self._thread and self._thread.is_alive():
            tprint("[GESTURE] Recognition stop timed out; thread still running")
            return
        self._cleanup(join_thread=False)
        tprint("[GESTURE] Recognition stopped")

    def _cleanup(self, join_thread: bool) -> None:
        if self._closed:
            return
        self.active = False
        self.stream.close()
        if self._hands:
            try:
                self._hands.close()
            except Exception:
                # MediaPipe may already be closed; ignore.
                pass
        self._closed = True
        if self.show_window:
            self._cv2.destroyAllWindows()
        if join_thread and self._thread and threading.current_thread() is not self._thread:
            self._thread.join(timeout=2)
        self._thread = None

    def is_running(self) -> bool:
        return bool((self._thread and self._thread.is_alive()) or self.active)

    def _is_enabled(self, label: str) -> bool:
        if not self.enabled_labels:
            return False
        return label in self.enabled_labels

    def set_enabled_labels(self, labels: set[str]) -> None:
        self.enabled_labels = labels

    def apply_runtime_settings(
        self,
        *,
        confidence_threshold: float | None = None,
        stable_frames: int | None = None,
        emit_cooldown_secs: float | None = None,
        emit_actions: bool | None = None,
        max_fps: float | None = None,
        watchdog_timeout_secs: float | None = None,
    ) -> None:
        if confidence_threshold is not None:
            self.confidence_threshold = float(confidence_threshold)
        if stable_frames is not None and stable_frames > 0:
            history = list(self._keypoint_history)
            self._keypoint_history = deque(history, maxlen=int(stable_frames))
        if emit_cooldown_secs is not None:
            self.emit_cooldown_secs = float(emit_cooldown_secs)
        if emit_actions is not None:
            self.emit_actions = bool(emit_actions)
        if max_fps is not None:
            self.max_fps = float(max_fps)
        if watchdog_timeout_secs is not None:
            self.watchdog_timeout_secs = float(watchdog_timeout_secs)
