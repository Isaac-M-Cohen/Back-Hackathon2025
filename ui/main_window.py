"""Main UI window placeholder."""


class MainWindow:
    def __init__(self) -> None:
        self.is_open = False

    def launch(self) -> None:
        self.is_open = True
        print("[UI] Main window launched")

    def close(self) -> None:
        self.is_open = False
        print("[UI] Main window closed")
