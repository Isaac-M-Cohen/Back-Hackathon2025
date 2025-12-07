"""Hand tracking implementation using OpenCV + MediaPipe."""

import cv2
import mediapipe as mp

from utils.file_utils import load_json
from video_module.video_stream import VideoStream
'''from config.gesture_config import'''


class HandTracker:
    def __init__(
        self,
        *,
        config_path: str = "config/gesture_config.json",
    ) -> None:
        self.active = False
        self._window_name = "Hand Tracking"

        cfg = load_json(config_path)
        self._max_hands = int(cfg.get("max_hands", 2))
        min_det = float(cfg.get("detection_threshold", 0.6))
        min_track = float(cfg.get("min_tracking_confidence", cfg.get("tracking_threshold", 0.6)))

        self._hands = mp.solutions.hands.Hands(
            static_image_mode=False,
            max_num_hands=self._max_hands,
            min_detection_confidence=min_det,
            min_tracking_confidence=min_track,
            model_complexity=1,
        )
        self._drawer = mp.solutions.drawing_utils
        self._cap = VideoStream()

    def start(self) -> None:
        """Open camera and stream landmarks to a window (press 'q' to quit)."""
        if self.active:
            return

        self._cap.open()
        self.active = True
        print("[HAND] Tracking started — press 'q' to exit.")
        try:
            self._run_loop()
        except KeyboardInterrupt:
            print("[HAND] Interrupted by user.")
        finally:
            self.stop()

    def _run_loop(self) -> None:
        drawing_spec = self._drawer.DrawingSpec(color=(0, 255, 0), thickness=2, circle_radius=2)
        connection_spec = self._drawer.DrawingSpec(color=(255, 0, 0), thickness=2)

        while self.active:
            ok, frame = self._cap.read()
            if not ok or frame is None:
                print("[HAND] Failed to read from camera.")
                break

            frame = cv2.flip(frame, 1)  # Mirror for user-friendly view.
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self._hands.process(rgb)

            if results.multi_hand_landmarks:
                for hand_landmarks in results.multi_hand_landmarks:
                    self._drawer.draw_landmarks(
                        frame,
                        hand_landmarks,
                        mp.solutions.hands.HAND_CONNECTIONS,
                        drawing_spec,
                        connection_spec,
                    )

            cv2.imshow(self._window_name, frame)

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break

    def stop(self) -> None:
        self.active = False
        self._cap.close()
        self._hands.close()
        cv2.destroyAllWindows()
        print("[HAND] Tracking stopped")
