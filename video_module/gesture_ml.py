"""Gesture dataset + collection helpers for TFLite-based classification."""

from __future__ import annotations

import csv
import json
import os
import sys
from pathlib import Path
from typing import Sequence
from video_module.tflite_pipeline import (
    POINT_HISTORY_LEN,
    calc_landmark_list,
    pre_process_landmark,
    pre_process_point_history,
)
from utils.log_utils import tprint
from utils.settings_store import deep_log, is_deep_logging


def _default_user_data_dir() -> Path:
    data_dir = os.getenv("USER_DATA_DIR") or os.getenv("DATA_DIR")
    if data_dir:
        data_path = Path(data_dir).expanduser()
        if data_path.is_absolute():
            return data_path / "user_data"
        if not getattr(sys, "frozen", False):
            return data_path / "user_data"

    if getattr(sys, "frozen", False):
        return Path.home() / "Library" / "Application Support" / "easy" / "user_data"

    return Path("user_data")


def _read_label_csv(path: Path) -> list[str]:
    if not path.exists():
        return []
    labels: list[str] = []
    with path.open(encoding="utf-8-sig") as fh:
        for row in csv.reader(fh):
            if not row:
                continue
            label = row[0].strip()
            if label:
                labels.append(label)
    return labels


def _write_label_csv(path: Path, labels: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        for label in labels:
            writer.writerow([label])


class GestureDataset:
    """Manages per-user datasets, labels, commands, and hotkeys."""

    def __init__(self, user_id: str, base_dir: str | Path | None = None) -> None:
        root = Path(base_dir) if base_dir is not None else _default_user_data_dir()
        self.base_dir = root / user_id
        self._ensure_base_dir_writable()
        deep_log(f"[DEEP][GESTURE] dataset base_dir={self.base_dir}")

        self.keypoint_dir = self.base_dir / "keypoint_classifier"
        self.point_history_dir = self.base_dir / "point_history_classifier"
        self.keypoint_csv = self.keypoint_dir / "keypoint.csv"
        self.point_history_csv = self.point_history_dir / "point_history.csv"
        self.keypoint_labels_path = self.keypoint_dir / "keypoint_classifier_label.csv"
        self.point_history_labels_path = (
            self.point_history_dir / "point_history_classifier_label.csv"
        )
        self.keypoint_model_path = self.keypoint_dir / "keypoint_classifier.tflite"
        self.point_history_model_path = self.point_history_dir / "point_history_classifier.tflite"

        self.hotkeys_path = self.base_dir / "hotkeys.json"
        self.commands_path = self.base_dir / "commands.json"
        self.command_steps_path = self.base_dir / "command_steps.json"
        self.enabled_path = self.base_dir / "enabled_gestures.json"

        self.hotkeys: dict[str, str] = {}
        self.commands: dict[str, str] = {}
        self.command_steps: dict[str, list[dict]] = {}
        self.enabled: set[str] = set()
        self._load_metadata()

    def _ensure_base_dir_writable(self) -> None:
        try:
            self.base_dir.mkdir(parents=True, exist_ok=True)
            probe = self.base_dir / ".write_test"
            probe.write_text("ok")
            probe.unlink(missing_ok=True)
            return
        except PermissionError:
            fallback_root = Path.home() / "Library" / "Application Support" / "easy" / "user_data"
            self.base_dir = fallback_root / self.base_dir.name
            self.base_dir.mkdir(parents=True, exist_ok=True)
            deep_log(f"[DEEP][GESTURE] dataset fallback base_dir={self.base_dir}")

    def _load_metadata(self) -> None:
        if self.hotkeys_path.exists():
            try:
                self.hotkeys = json.loads(self.hotkeys_path.read_text())
            except json.JSONDecodeError:
                self.hotkeys = {}
        if self.commands_path.exists():
            try:
                self.commands = json.loads(self.commands_path.read_text())
            except json.JSONDecodeError:
                self.commands = {}
        if self.command_steps_path.exists():
            try:
                self.command_steps = json.loads(self.command_steps_path.read_text())
            except json.JSONDecodeError:
                self.command_steps = {}
        if self.enabled_path.exists():
            try:
                items = json.loads(self.enabled_path.read_text())
                self.enabled = {str(lbl) for lbl in items}
            except json.JSONDecodeError:
                self.enabled = set()

    def ensure_presets(self) -> bool:
        presets_root = Path("data/presets")
        if not presets_root.exists():
            module_root = Path(__file__).resolve().parents[1]
            presets_root = module_root / "data" / "presets"
        presets_csv = presets_root / "keypoint.csv"
        presets_labels = presets_root / "keypoint_classifier_label.csv"
        point_labels = presets_root / "point_history_classifier_label.csv"
        keypoint_model = presets_root / "keypoint_classifier.tflite"
        point_model = presets_root / "point_history_classifier.tflite"
        deep_log(f"[DEEP][GESTURE] presets_root={presets_root}")
        if not presets_csv.exists() or not presets_labels.exists():
            deep_log(
                "[DEEP][GESTURE] presets missing "
                f"keypoint_csv={presets_csv.exists()} "
                f"keypoint_labels={presets_labels.exists()}"
            )
            return False
        if not self.keypoint_csv.exists():
            self.keypoint_dir.mkdir(parents=True, exist_ok=True)
            self.keypoint_csv.write_text(presets_csv.read_text())
        if not self.keypoint_labels_path.exists():
            self.keypoint_labels_path.write_text(presets_labels.read_text())
        if point_labels.exists() and not self.point_history_labels_path.exists():
            self.point_history_labels_path.parent.mkdir(parents=True, exist_ok=True)
            self.point_history_labels_path.write_text(point_labels.read_text())
        if keypoint_model.exists() and not self.keypoint_model_path.exists():
            self.keypoint_model_path.parent.mkdir(parents=True, exist_ok=True)
            self.keypoint_model_path.write_bytes(keypoint_model.read_bytes())
        if point_model.exists() and not self.point_history_model_path.exists():
            self.point_history_model_path.parent.mkdir(parents=True, exist_ok=True)
            self.point_history_model_path.write_bytes(point_model.read_bytes())
        if not self.enabled_path.exists():
            labels = set(self.keypoint_labels()) | set(self.point_history_labels())
            if labels:
                self.enabled = set(labels)
                self.enabled_path.write_text(json.dumps(sorted(self.enabled), indent=2))
        return True

    def keypoint_labels(self) -> list[str]:
        return _read_label_csv(self.keypoint_labels_path)

    def point_history_labels(self) -> list[str]:
        return _read_label_csv(self.point_history_labels_path)

    def _ensure_label(self, label: str, *, kind: str) -> int:
        if kind == "keypoint":
            labels = self.keypoint_labels()
            path = self.keypoint_labels_path
        elif kind == "point_history":
            labels = self.point_history_labels()
            path = self.point_history_labels_path
        else:
            raise ValueError(f"Unknown label kind: {kind}")

        if label not in labels:
            labels.append(label)
            _write_label_csv(path, labels)
        return labels.index(label)

    def append_keypoint_sample(self, label: str, feature_list: Sequence[float]) -> None:
        label_id = self._ensure_label(label, kind="keypoint")
        self.keypoint_dir.mkdir(parents=True, exist_ok=True)
        with self.keypoint_csv.open("a", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow([label_id, *feature_list])

    def append_point_history_sample(self, label: str, feature_list: Sequence[float]) -> None:
        label_id = self._ensure_label(label, kind="point_history")
        self.point_history_dir.mkdir(parents=True, exist_ok=True)
        with self.point_history_csv.open("a", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow([label_id, *feature_list])

    def list_gestures(self) -> list[dict]:
        labels = sorted(set(self.keypoint_labels()) | set(self.point_history_labels()))
        return [
            {
                "label": label,
                "hotkey": self.hotkeys.get(label, ""),
                "command": self.commands.get(label, ""),
                "enabled": label in self.enabled,
            }
            for label in labels
        ]

    def set_hotkey(self, label: str, hotkey: str | None) -> None:
        if hotkey:
            self.hotkeys[label] = hotkey
        else:
            self.hotkeys.pop(label, None)
        self.hotkeys_path.write_text(json.dumps(self.hotkeys, indent=2))

    def set_command(self, label: str, command: str | None) -> None:
        if command:
            self.commands[label] = command
        else:
            self.commands.pop(label, None)
        self.commands_path.write_text(json.dumps(self.commands, indent=2))

    def set_command_steps(self, label: str, steps: list[dict] | None) -> None:
        if steps:
            self.command_steps[label] = steps
        else:
            self.command_steps.pop(label, None)
        self.command_steps_path.write_text(json.dumps(self.command_steps, indent=2))

    def set_enabled(self, label: str, enabled: bool) -> None:
        if enabled:
            self.enabled.add(label)
        else:
            self.enabled.discard(label)
        self.enabled_path.write_text(json.dumps(sorted(self.enabled), indent=2))

    def is_enabled(self, label: str) -> bool:
        return label in self.enabled

    def remove_label(self, label: str) -> None:
        self._remove_label_from_csv(self.keypoint_csv, self.keypoint_labels_path, label)
        self._remove_label_from_csv(
            self.point_history_csv, self.point_history_labels_path, label
        )
        self.hotkeys.pop(label, None)
        self.commands.pop(label, None)
        self.command_steps.pop(label, None)
        self.enabled.discard(label)
        self.hotkeys_path.write_text(json.dumps(self.hotkeys, indent=2))
        self.commands_path.write_text(json.dumps(self.commands, indent=2))
        self.command_steps_path.write_text(json.dumps(self.command_steps, indent=2))
        self.enabled_path.write_text(json.dumps(sorted(self.enabled), indent=2))

    def _remove_label_from_csv(
        self, data_path: Path, labels_path: Path, label: str
    ) -> None:
        labels = _read_label_csv(labels_path)
        if label not in labels:
            return
        label_idx = labels.index(label)
        labels.pop(label_idx)
        _write_label_csv(labels_path, labels)

        if not data_path.exists():
            return
        rows: list[list[str]] = []
        with data_path.open(encoding="utf-8") as fh:
            for row in csv.reader(fh):
                if not row:
                    continue
                try:
                    idx = int(row[0])
                except ValueError:
                    continue
                if idx == label_idx:
                    continue
                if idx > label_idx:
                    row[0] = str(idx - 1)
                rows.append(row)
        data_path.parent.mkdir(parents=True, exist_ok=True)
        with data_path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerows(rows)


class GestureCollector:
    """Collects static keypoints and point history samples using MediaPipe Hands."""

    def __init__(
        self,
        *,
        device_index: int = 0,
        detection_confidence: float = 0.7,
        tracking_confidence: float = 0.5,
        show_preview: bool = False,
    ) -> None:
        self.show_preview = show_preview
        try:
            import mediapipe as mp
            import cv2
        except ImportError as exc:
            raise RuntimeError(
                "MediaPipe is required for gesture collection. Install mediapipe>=0.10."
            ) from exc
        mp_solutions = getattr(mp, "solutions", None)
        if mp_solutions is None:
            raise RuntimeError(
                "MediaPipe is missing 'solutions'. Install mediapipe>=0.10 in the active interpreter."
            )
        from video_module.video_stream import VideoStream

        self._cv2 = cv2
        self._hand_connections = mp_solutions.hands.HAND_CONNECTIONS
        self.stream = VideoStream(device_index)
        self._hands = mp_solutions.hands.Hands(
            static_image_mode=False,
            max_num_hands=1,
            min_detection_confidence=detection_confidence,
            min_tracking_confidence=tracking_confidence,
        )
        self._drawer = mp_solutions.drawing_utils

    def collect_static(
        self, dataset: GestureDataset, label: str, target_frames: int = 60
    ) -> int:
        collected = 0
        self.stream.open()
        tprint(f"[COLLECT] Static gesture='{label}' target_frames={target_frames}")
        try:
            while collected < target_frames:
                ok, frame = self.stream.read()
                if not ok or frame is None:
                    tprint("[COLLECT] Camera read failed")
                    break
                frame = self._cv2.flip(frame, 1)
                results = self._hands.process(
                    self._cv2.cvtColor(frame, self._cv2.COLOR_BGR2RGB)
                )
                if results.multi_hand_landmarks:
                    hand_landmarks = results.multi_hand_landmarks[0]
                    landmark_list = calc_landmark_list(frame, hand_landmarks)
                    features = pre_process_landmark(landmark_list)
                    dataset.append_keypoint_sample(label, features)
                    collected += 1
                    self._drawer.draw_landmarks(
                        frame,
                        hand_landmarks,
                        self._hand_connections,
                    )
                if self.show_preview:
                    self._cv2.putText(
                        frame,
                        f"{label} frames: {collected}/{target_frames}",
                        (10, 30),
                        self._cv2.FONT_HERSHEY_SIMPLEX,
                        0.7,
                        (0, 255, 0),
                        2,
                    )
                    self._cv2.imshow("Collect Static Gesture", frame)
                    if (self._cv2.waitKey(1) & 0xFF) == ord("q"):
                        break
        finally:
            self.stream.close()
            if self.show_preview:
                self._cv2.destroyAllWindows()
        return collected

    def collect_dynamic(
        self,
        dataset: GestureDataset,
        label: str,
        *,
        repetitions: int = 5,
        show_preview: bool | None = None,
    ) -> int:
        collected = 0
        self.stream.open()
        tprint(f"[COLLECT] Dynamic gesture='{label}' repetitions={repetitions}")
        if show_preview is None:
            show_preview = self.show_preview
        try:
            for rep in range(repetitions):
                point_history: list[list[int]] = []
                while len(point_history) < POINT_HISTORY_LEN:
                    ok, frame = self.stream.read()
                    if not ok or frame is None:
                        tprint("[COLLECT] Camera read failed")
                        return collected
                    frame = self._cv2.flip(frame, 1)
                    results = self._hands.process(
                        self._cv2.cvtColor(frame, self._cv2.COLOR_BGR2RGB)
                    )
                    if results.multi_hand_landmarks:
                        hand_landmarks = results.multi_hand_landmarks[0]
                        landmark_list = calc_landmark_list(frame, hand_landmarks)
                        point_history.append(landmark_list[8])
                        self._drawer.draw_landmarks(
                            frame,
                            hand_landmarks,
                            self._hand_connections,
                        )
                    if show_preview:
                        self._cv2.putText(
                            frame,
                            f"{label} rep {rep+1}/{repetitions} {len(point_history)}/{POINT_HISTORY_LEN}",
                            (10, 30),
                            self._cv2.FONT_HERSHEY_SIMPLEX,
                            0.7,
                            (255, 255, 0),
                            2,
                        )
                        self._cv2.imshow("Collect Dynamic Gesture", frame)
                        if (self._cv2.waitKey(1) & 0xFF) == ord("q"):
                            return collected

                features = pre_process_point_history(frame, point_history)
                dataset.append_point_history_sample(label, features)
                collected += 1
        finally:
            self.stream.close()
            if show_preview:
                self._cv2.destroyAllWindows()
        return collected
