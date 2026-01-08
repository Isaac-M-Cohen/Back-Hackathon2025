from gesture_module.gesture_recognizer import RealTimeGestureRecognizer
from gesture_module.workflow import GestureWorkflow


def __getattr__(name):
    if name == "GestureDetector":
        from gesture_module.gesture_detector import GestureDetector

        return GestureDetector
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "GestureDetector",
    "RealTimeGestureRecognizer",
    "GestureWorkflow",
]
