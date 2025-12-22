"""End-to-end gesture pipeline: normalization, collection, training, and inference.

This prototype keeps everything CPU-only, uses MediaPipe Hands landmarks as input
features (63 floats per frame), and trains a small MLP for user-defined gestures.
It supports static gestures (single-frame samples) and dynamic gestures
(short sequences flattened into a fixed window). Model + dataset are stored under:

  user_data/<user_id>/
    X.npy
    y.npy
    labels.json
    model.pkl
"""

from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import cv2
import joblib
import mediapipe as mp
import numpy as np
from sklearn.neural_network import MLPClassifier

from video_module.video_stream import VideoStream

_HAND_LANDMARKS = 21
_LANDMARK_DIMS = 3  # x, y, z


def normalize_landmarks(
    landmarks: Sequence, handedness: str | None = None, *, mirror_left: bool = True
) -> np.ndarray:
    """Translate wrist to origin and scale by wrist->middle_mcp distance.

    Returns a flat (63,) float32 vector. Optionally mirrors left-hand x coords so
    left/right gestures map to the same space.
    """
    if len(landmarks) != _HAND_LANDMARKS:
        raise ValueError(f"Expected {_HAND_LANDMARKS} landmarks, got {len(landmarks)}")

    coords = np.array([[lm.x, lm.y, lm.z] for lm in landmarks], dtype=np.float32)
    wrist = coords[0]
    coords -= wrist  # translate wrist to origin

    ref = coords[9]  # middle finger MCP
    scale = float(np.linalg.norm(ref[:2])) or 1.0
    coords /= scale

    is_left = handedness and handedness.lower().startswith("left")
    if mirror_left and is_left:
        coords[:, 0] *= -1.0

    return coords.flatten().astype(np.float32)


def _to_window(frames: Sequence[np.ndarray], window_size: int) -> np.ndarray:
    """Pad/trim a list of frame features to a fixed window and flatten."""
    if not frames:
        raise ValueError("frames cannot be empty")
    window: list[np.ndarray] = list(frames[-window_size:])
    while len(window) < window_size:
        window.append(window[-1])
    stacked = np.stack(window, axis=0)
    return stacked.flatten().astype(np.float32)


@dataclass
class ModelArtifacts:
    model: MLPClassifier
    labels: list[str]  # index -> label
    label_to_idx: dict[str, int]


class GestureDataset:
    """Manages per-user dataset and model storage."""

    def __init__(self, user_id: str, base_dir: str | Path = "user_data") -> None:
        self.base_dir = Path(base_dir) / user_id
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.X_path = self.base_dir / "X.npy"
        self.y_path = self.base_dir / "y.npy"
        self.labels_path = self.base_dir / "labels.json"
        self.model_path = self.base_dir / "model.pkl"

        self.labels: list[str] = []
        self.label_to_idx: dict[str, int] = {}
        self.X: np.ndarray | None = None
        self.y: np.ndarray | None = None
        self._load_metadata()
        self._load_arrays()

    def _load_metadata(self) -> None:
        if self.labels_path.exists():
            self.labels = json.loads(self.labels_path.read_text())
            self.label_to_idx = {lbl: i for i, lbl in enumerate(self.labels)}
        else:
            self.labels = []
            self.label_to_idx = {}

    def _load_arrays(self) -> None:
        if self.X_path.exists() and self.y_path.exists():
            self.X = np.load(self.X_path)
            self.y = np.load(self.y_path)
        else:
            self.X = None
            self.y = None

    def _ensure_label(self, label: str) -> int:
        if label not in self.label_to_idx:
            self.label_to_idx[label] = len(self.labels)
            self.labels.append(label)
        return self.label_to_idx[label]

    def add_samples(self, label: str, samples: Iterable[np.ndarray]) -> None:
        """Append samples for a label. Samples must already be flattened windows."""
        data = np.vstack(list(samples))
        idx = self._ensure_label(label)
        targets = np.full(shape=(len(data),), fill_value=idx, dtype=np.int64)
        if self.X is None or self.y is None:
            self.X = data
            self.y = targets
        else:
            self.X = np.concatenate([self.X, data], axis=0)
            self.y = np.concatenate([self.y, targets], axis=0)

    def save(self) -> None:
        if self.X is None or self.y is None:
            raise RuntimeError("No samples to save")
        np.save(self.X_path, self.X.astype(np.float32))
        np.save(self.y_path, self.y.astype(np.int64))
        self.labels_path.write_text(json.dumps(self.labels, indent=2))

    def save_model(self, artifacts: ModelArtifacts) -> None:
        joblib.dump(
            {"model": artifacts.model, "labels": artifacts.labels},
            self.model_path,
        )

    def load_model(self) -> ModelArtifacts | None:
        if not self.model_path.exists():
            return None
        blob = joblib.load(self.model_path)
        labels = list(blob["labels"])
        label_to_idx = {lbl: i for i, lbl in enumerate(labels)}
        return ModelArtifacts(model=blob["model"], labels=labels, label_to_idx=label_to_idx)


class GestureTrainer:
    """Trains a small MLP classifier from scratch each time samples change."""

    def __init__(
        self,
        window_size: int = 30,
        hidden_layers: tuple[int, int] = (64, 32),
        max_iter: int = 150,
    ) -> None:
        self.window_size = window_size
        self.hidden_layers = hidden_layers
        self.max_iter = max_iter

    def train(self, dataset: GestureDataset) -> ModelArtifacts:
        if dataset.X is None or dataset.y is None:
            raise RuntimeError("No samples available to train model")

        model = MLPClassifier(
            hidden_layer_sizes=self.hidden_layers,
            activation="relu",
            solver="adam",
            max_iter=self.max_iter,
            random_state=42,
        )
        model.fit(dataset.X, dataset.y)
        return ModelArtifacts(model=model, labels=list(dataset.labels), label_to_idx=dict(dataset.label_to_idx))


class GestureRecognizer:
    """Runtime inference with confidence thresholding and temporal smoothing."""

    def __init__(
        self,
        artifacts: ModelArtifacts,
        window_size: int = 30,
        confidence_threshold: float = 0.6,
        stable_frames: int = 5,
    ) -> None:
        self.artifacts = artifacts
        self.window_size = window_size
        self.confidence_threshold = confidence_threshold
        self.stable_frames = stable_frames
        self.buffer: deque[np.ndarray] = deque(maxlen=window_size)
        self._current_label: str | None = None
        self._streak: int = 0

    def observe(self, frame_features: np.ndarray) -> tuple[str, float]:
        """Add a normalized frame and return the smoothed prediction."""
        self.buffer.append(frame_features)
        if len(self.buffer) == 0:
            return "NONE", 0.0
        features = _to_window(list(self.buffer), self.window_size).reshape(1, -1)
        probs = self.artifacts.model.predict_proba(features)[0]
        best_idx = int(np.argmax(probs))
        best_label = self.artifacts.labels[best_idx]
        best_conf = float(probs[best_idx])

        candidate = best_label if best_conf >= self.confidence_threshold else "NONE"
        if candidate == self._current_label:
            self._streak += 1
        else:
            self._current_label = candidate
            self._streak = 1

        if candidate == "NONE":
            return "NONE", best_conf

        if self._streak >= self.stable_frames:
            return candidate, best_conf
        return "NONE", best_conf


class GestureCollector:
    """Handles webcam capture and sample collection for training."""

    def __init__(
        self,
        window_size: int = 30,
        *,
        mirror_left: bool = True,
        device_index: int = 0,
        detection_confidence: float = 0.6,
        tracking_confidence: float = 0.6,
    ) -> None:
        self.window_size = window_size
        self.mirror_left = mirror_left
        self.stream = VideoStream(device_index)
        self._drawer = mp.solutions.drawing_utils
        self._hands = mp.solutions.hands.Hands(
            static_image_mode=False,
            max_num_hands=1,
            min_detection_confidence=detection_confidence,
            min_tracking_confidence=tracking_confidence,
            model_complexity=1,
        )

    def _read(self) -> tuple[bool, np.ndarray]:
        ok, frame = self.stream.read()
        if not ok:
            return False, frame
        return True, frame

    def _process(self, frame: np.ndarray):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        return self._hands.process(rgb)

    def _extract_features(self, results) -> tuple[np.ndarray | None, str | None]:
        if not results.multi_hand_landmarks:
            return None, None
        hand_landmarks = results.multi_hand_landmarks[0]
        handedness = None
        if results.multi_handedness:
            handedness = results.multi_handedness[0].classification[0].label
        features = normalize_landmarks(
            hand_landmarks.landmark,
            handedness=handedness,
            mirror_left=self.mirror_left,
        )
        return features, handedness

    def collect_static(
        self, gesture_label: str, target_frames: int = 60
    ) -> list[np.ndarray]:
        """Collect individual frames while the user holds a pose."""
        samples: list[np.ndarray] = []
        self.stream.open()
        print(f"[COLLECT] Static gesture='{gesture_label}' target_frames={target_frames}")
        print("          Hold the gesture steady. Press 'q' to abort.")
        try:
            while len(samples) < target_frames:
                ok, frame = self._read()
                if not ok or frame is None:
                    print("[COLLECT] Camera read failed")
                    break

                results = self._process(frame)
                features, _hand = self._extract_features(results)
                if features is not None:
                    samples.append(features)
                    if results.multi_hand_landmarks:
                        self._drawer.draw_landmarks(
                            frame,
                            results.multi_hand_landmarks[0],
                            mp.solutions.hands.HAND_CONNECTIONS,
                        )

                cv2.putText(
                    frame,
                    f"{gesture_label} frames: {len(samples)}/{target_frames}",
                    (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (0, 255, 0),
                    2,
                )
                cv2.imshow("Collect Static Gesture", frame)
                if (cv2.waitKey(1) & 0xFF) == ord("q"):
                    break
        finally:
            self.stream.close()
            cv2.destroyAllWindows()

        if samples:
            # Convert each single frame into a padded window for training.
            return [_to_window([s], self.window_size) for s in samples]
        return []

    def collect_dynamic(
        self,
        gesture_label: str,
        *,
        repetitions: int = 5,
        sequence_length: int = 30,
    ) -> list[np.ndarray]:
        """Collect short sequences (e.g., swipes). Press 's' to start each capture."""
        sequences: list[np.ndarray] = []
        self.stream.open()
        print(
            f"[COLLECT] Dynamic gesture='{gesture_label}' repetitions={repetitions} "
            f"sequence_length={sequence_length}"
        )
        print("          Press 's' to record each repetition, 'q' to abort.")
        try:
            for rep in range(repetitions):
                buffer: list[np.ndarray] = []
                recording = False
                while True:
                    ok, frame = self._read()
                    if not ok or frame is None:
                        print("[COLLECT] Camera read failed")
                        break

                    results = self._process(frame)
                    features, _hand = self._extract_features(results)
                    if recording and features is not None:
                        buffer.append(features)
                    if results.multi_hand_landmarks:
                        self._drawer.draw_landmarks(
                            frame,
                            results.multi_hand_landmarks[0],
                            mp.solutions.hands.HAND_CONNECTIONS,
                        )

                    status = f"{gesture_label} rep {rep+1}/{repetitions}"
                    if recording:
                        status += f" recording {len(buffer)}/{sequence_length}"
                    else:
                        status += " press 's' to start"

                    cv2.putText(
                        frame,
                        status,
                        (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.7,
                        (255, 255, 0),
                        2,
                    )
                    cv2.imshow("Collect Dynamic Gesture", frame)
                    key = cv2.waitKey(1) & 0xFF

                    if key == ord("q"):
                        return sequences
                    if not recording and key == ord("s"):
                        recording = True
                        buffer = []
                    if recording and len(buffer) >= sequence_length:
                        window = _to_window(buffer, self.window_size)
                        sequences.append(window)
                        print(
                            f"[COLLECT] captured rep {rep+1} with {len(buffer)} frames"
                        )
                        break
        finally:
            self.stream.close()
            cv2.destroyAllWindows()

        return sequences
