"""TFLite classifiers for static keypoints and point history gestures."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import numpy as np


def _load_interpreter(model_path: Path):
    try:
        from tflite_runtime.interpreter import Interpreter  # type: ignore
    except ImportError:
        try:
            from tensorflow.lite.python.interpreter import Interpreter  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "TFLite interpreter not available. Install tflite-runtime or tensorflow."
            ) from exc
    return Interpreter(model_path=str(model_path))


class KeyPointClassifier:
    def __init__(self, model_path: Path) -> None:
        if not model_path.exists():
            raise FileNotFoundError(f"Missing keypoint model: {model_path}")
        self._interpreter = _load_interpreter(model_path)
        self._interpreter.allocate_tensors()
        self._input_details = self._interpreter.get_input_details()
        self._output_details = self._interpreter.get_output_details()

    def __call__(self, landmark_list: Sequence[float]) -> tuple[int, float]:
        input_data = np.array([landmark_list], dtype=np.float32)
        self._interpreter.set_tensor(self._input_details[0]["index"], input_data)
        self._interpreter.invoke()
        output = self._interpreter.get_tensor(self._output_details[0]["index"])[0]
        idx = int(np.argmax(output))
        return idx, float(output[idx])


class PointHistoryClassifier:
    def __init__(
        self,
        model_path: Path,
        *,
        score_threshold: float = 0.5,
        invalid_value: int = 0,
    ) -> None:
        if not model_path.exists():
            raise FileNotFoundError(f"Missing point history model: {model_path}")
        self._interpreter = _load_interpreter(model_path)
        self._interpreter.allocate_tensors()
        self._input_details = self._interpreter.get_input_details()
        self._output_details = self._interpreter.get_output_details()
        self._score_threshold = score_threshold
        self._invalid_value = invalid_value

    def __call__(self, point_history_list: Sequence[float]) -> tuple[int, float]:
        input_data = np.array([point_history_list], dtype=np.float32)
        self._interpreter.set_tensor(self._input_details[0]["index"], input_data)
        self._interpreter.invoke()
        output = self._interpreter.get_tensor(self._output_details[0]["index"])[0]
        idx = int(np.argmax(output))
        score = float(output[idx])
        if score < self._score_threshold:
            return self._invalid_value, score
        return idx, score
