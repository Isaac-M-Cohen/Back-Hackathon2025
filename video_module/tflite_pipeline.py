"""MediaPipe landmark preprocessing helpers for TFLite classifiers."""

from __future__ import annotations

import copy
import itertools
from collections import deque
from typing import Sequence

POINT_HISTORY_LEN = 16


def calc_landmark_list(image, landmarks) -> list[list[int]]:
    image_width, image_height = image.shape[1], image.shape[0]
    landmark_point: list[list[int]] = []
    for _, landmark in enumerate(landmarks.landmark):
        landmark_x = min(int(landmark.x * image_width), image_width - 1)
        landmark_y = min(int(landmark.y * image_height), image_height - 1)
        landmark_point.append([landmark_x, landmark_y])
    return landmark_point


def pre_process_landmark(landmark_list: Sequence[Sequence[int]]) -> list[float]:
    temp_landmark_list = copy.deepcopy(landmark_list)
    base_x, base_y = 0, 0
    for index, landmark_point in enumerate(temp_landmark_list):
        if index == 0:
            base_x, base_y = landmark_point[0], landmark_point[1]
        temp_landmark_list[index][0] = temp_landmark_list[index][0] - base_x
        temp_landmark_list[index][1] = temp_landmark_list[index][1] - base_y

    temp_landmark_list = list(itertools.chain.from_iterable(temp_landmark_list))
    max_value = max(list(map(abs, temp_landmark_list))) if temp_landmark_list else 1
    if max_value == 0:
        max_value = 1
    return [value / max_value for value in temp_landmark_list]


def pre_process_point_history(image, point_history: Sequence[Sequence[int]]) -> list[float]:
    image_width, image_height = image.shape[1], image.shape[0]
    temp_point_history = copy.deepcopy(point_history)
    base_x, base_y = 0, 0
    for index, point in enumerate(temp_point_history):
        if index == 0:
            base_x, base_y = point[0], point[1]
        temp_point_history[index][0] = (temp_point_history[index][0] - base_x) / image_width
        temp_point_history[index][1] = (temp_point_history[index][1] - base_y) / image_height
    return list(itertools.chain.from_iterable(temp_point_history))


class PointHistoryBuffer:
    def __init__(self, maxlen: int = POINT_HISTORY_LEN) -> None:
        self._history = deque(maxlen=maxlen)

    def append(self, point: Sequence[int]) -> None:
        self._history.append(list(point))

    def zeros(self) -> None:
        self._history.append([0, 0])

    def as_list(self) -> list[list[int]]:
        return list(self._history)

    def __len__(self) -> int:
        return len(self._history)
