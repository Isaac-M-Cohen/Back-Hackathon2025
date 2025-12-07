"""Thin wrapper around OpenCV VideoCapture."""

import cv2


class VideoStream:
    def __init__(self, device_index: int = 0) -> None:
        self.device_index = device_index
        self._cap = None

    def open(self) -> None:
        if self._cap is not None:
            return

        self._cap = cv2.VideoCapture(self.device_index)
        if not self._cap.isOpened():
            self._cap.release()
            self._cap = None
            raise RuntimeError(f"Unable to open camera at index {self.device_index}.")

    def read(self):
        if self._cap is None:
            raise RuntimeError("VideoStream not opened.")
        return self._cap.read()

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None
