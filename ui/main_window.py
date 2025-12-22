"""Main UI window placeholder.

Attach your real frontend here. The `gesture_workflow` argument exposes methods to:
  - collect_static(label, target_frames)
  - collect_dynamic(label, repetitions, sequence_length)
  - train_and_save()
  - start_recognition(controller, confidence_threshold, stable_frames, show_window)
  - stop_recognition()
Keep the camera closed until you call one of those methods (e.g., when adding a gesture).
"""


class MainWindow:
    def __init__(self, gesture_workflow=None) -> None:
        self.is_open = False
        self.gesture_workflow = gesture_workflow

    def launch(self) -> None:
        self.is_open = True
        print("[UI] Main window launched (attach your frontend here)")

    def close(self) -> None:
        self.is_open = False
        print("[UI] Main window closed")
