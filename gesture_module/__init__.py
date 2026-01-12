def __getattr__(name):
    if name == "GestureDetector":
        from gesture_module.gesture_detector import GestureDetector

        return GestureDetector
    if name == "RealTimeGestureRecognizer":
        from gesture_module.gesture_recognizer import RealTimeGestureRecognizer

        return RealTimeGestureRecognizer
    if name == "GestureWorkflow":
        from gesture_module.workflow import GestureWorkflow

        return GestureWorkflow
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "GestureDetector",
    "RealTimeGestureRecognizer",
    "GestureWorkflow",
]
