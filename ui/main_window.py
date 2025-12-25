"""PySide6 native UI for the easy desktop app - Enhanced version."""

from __future__ import annotations

import os
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from command_controller.controller import CommandController
from gesture_module.workflow import GestureWorkflow
from utils.file_utils import load_json


@dataclass(frozen=True)
class PresetGesture:
    gesture_id: str
    name: str
    duration: float


PRESET_GESTURES = [
    PresetGesture("thumbs_up", "Thumbs Up", 1.2),
    PresetGesture("peace_sign", "Peace Sign", 1.0),
    PresetGesture("wave", "Wave", 1.5),
    PresetGesture("fist", "Closed Fist", 1.0),
    PresetGesture("open_palm", "Open Palm", 1.0),
    PresetGesture("point_up", "Point Up", 1.0),
    PresetGesture("swipe_left", "Swipe Left", 1.3),
    PresetGesture("swipe_right", "Swipe Right", 1.3),
]


APP_STYLES = """
QWidget {
    background: #f8fafc;
    color: #0f172a;
    font-size: 14px;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Roboto", "Oxygen", "Ubuntu", sans-serif;
}

QLabel#TitleLabel {
    font-size: 24px;
    font-weight: 300;
    letter-spacing: -0.5px;
    color: #1e293b;
}

QFrame#MainCard {
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 16px;
}

QFrame#Banner {
    border-radius: 8px;
    padding: 12px 16px;
}

QFrame#Banner[variant="error"] {
    background: #fef2f2;
    border: 1px solid #fecaca;
}

QFrame#Banner QLabel {
    color: #991b1b;
    font-size: 13px;
}

QFrame#Banner[variant="success"] {
    background: #ecfdf5;
    border: 1px solid #a7f3d0;
}

QFrame#Banner[variant="success"] QLabel {
    color: #065f46;
    font-size: 13px;
}

QPushButton {
    background: #f1f5f9;
    border: 1px solid #cbd5e1;
    border-radius: 8px;
    padding: 8px 16px;
    font-size: 13px;
    font-weight: 500;
}

QPushButton:hover {
    background: #e2e8f0;
    border-color: #94a3b8;
}

QPushButton:pressed {
    background: #cbd5e1;
}

QPushButton#PrimaryButton {
    background: #3b82f6;
    color: white;
    border: none;
    padding: 12px 24px;
    font-weight: 500;
}

QPushButton#PrimaryButton:hover {
    background: #2563eb;
}

QPushButton#PrimaryButton:pressed {
    background: #1d4ed8;
}

QPushButton#PrimaryButton[highlight="true"] {
    background: #fef3c7;
    color: #92400e;
    border: 1px solid #f59e0b;
}

QPushButton#DangerButton {
    background: #fef2f2;
    color: #dc2626;
    border: 1px solid #fecaca;
    padding: 6px 12px;
    font-size: 12px;
}

QPushButton#DangerButton:hover {
    background: #fee2e2;
    border-color: #fca5a5;
}

QPushButton#RunButton {
    padding: 10px 20px;
    border-radius: 8px;
    font-weight: 500;
    font-size: 13px;
}

QPushButton#RunButton[active="true"] {
    background: #22c55e;
    color: white;
    border: none;
}

QPushButton#RunButton[active="true"]:hover {
    background: #16a34a;
}

QPushButton#RunButton[active="false"] {
    background: #e2e8f0;
    color: #475569;
    border: 1px solid #cbd5e1;
}

QPushButton#RunButton[active="false"]:hover {
    background: #cbd5e1;
}

QTableWidget {
    border: none;
    background: transparent;
    gridline-color: transparent;
}

QTableWidget::item {
    padding: 16px 24px;
    border-bottom: 1px solid #f1f5f9;
}

QTableWidget::item:last {
    border-bottom: none;
}

QHeaderView::section {
    background: transparent;
    border: none;
    padding: 0px;
}

QLineEdit, QKeySequenceEdit {
    padding: 10px 12px;
    border: 2px solid #e2e8f0;
    border-radius: 8px;
    background: white;
    font-size: 13px;
}

QLineEdit:focus, QKeySequenceEdit:focus {
    border-color: #3b82f6;
    outline: none;
}

QDialog {
    background: white;
}

QListWidget {
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    background: white;
    padding: 4px;
}

QListWidget::item {
    border-radius: 6px;
    padding: 12px;
    margin: 2px;
}

QListWidget::item:hover {
    background: #f1f5f9;
}

QListWidget::item:selected {
    background: #eff6ff;
    color: #1e40af;
    border: 1px solid #bfdbfe;
}

QRadioButton {
    spacing: 8px;
}

QRadioButton::indicator {
    width: 18px;
    height: 18px;
    border-radius: 9px;
    border: 2px solid #cbd5e1;
    background: white;
}

QRadioButton::indicator:checked {
    background: #3b82f6;
    border-color: #3b82f6;
}

QRadioButton::indicator:hover {
    border-color: #3b82f6;
}

QLabel#GesturePreview {
    background: #f1f5f9;
    border-radius: 8px;
    color: #64748b;
    font-size: 11px;
}

QLabel#HotkeyBadge {
    background: #f1f5f9;
    border-radius: 6px;
    padding: 6px 12px;
    color: #475569;
    font-size: 13px;
    font-weight: 500;
}

QLabel#BuildStamp {
    color: #94a3b8;
    font-size: 11px;
}

QStatusBar {
    background: transparent;
    border: none;
}
"""

_APP_SETTINGS = load_json("config/app_settings.json")
APP_NAME = _APP_SETTINGS.get("app_name", "Gesture Control")


def _build_stamp() -> str:
    """Return a short build stamp to compare running UI versions."""
    try:
        path = Path(__file__).resolve()
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(path.stat().st_mtime))
        return f"Build: {path.name} {ts} | Exec: {Path(sys.executable).name}"
    except Exception:
        return f"Build: {Path(__file__).name} | Exec: {Path(sys.executable).name}"


def _ensure_qt_plugin_path() -> None:
    """Ensure Qt can locate platform plugins in PySide6 installs."""
    if os.getenv("QT_QPA_PLATFORM_PLUGIN_PATH"):
        return
    try:
        plugin_root = QtCore.QLibraryInfo.path(QtCore.QLibraryInfo.PluginsPath)
    except Exception:
        return
    if not plugin_root:
        return
    platforms_path = os.path.join(plugin_root, "platforms")
    os.environ.setdefault("QT_QPA_PLATFORM_PLUGIN_PATH", platforms_path)
    os.environ.setdefault("QT_PLUGIN_PATH", plugin_root)


class PresetDialog(QtWidgets.QDialog):
    def __init__(self, presets: list[PresetGesture], parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Choose a Gesture")
        self.setModal(True)
        self.setMinimumWidth(480)
        self._presets = presets
        self.selected_preset: PresetGesture | None = None

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QtWidgets.QLabel("Choose a Gesture")
        title.setObjectName("TitleLabel")
        layout.addWidget(title)

        self.list_widget = QtWidgets.QListWidget()
        self.list_widget.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        for preset in presets:
            item = QtWidgets.QListWidgetItem(preset.name)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, preset)
            self.list_widget.addItem(item)
        self.list_widget.itemDoubleClicked.connect(self._accept_selected)
        layout.addWidget(self.list_widget)

        button_row = QtWidgets.QHBoxLayout()
        button_row.addStretch()
        cancel_btn = QtWidgets.QPushButton("Cancel")
        cancel_btn.setFixedWidth(100)
        cancel_btn.clicked.connect(self.reject)
        select_btn = QtWidgets.QPushButton("Select")
        select_btn.setObjectName("PrimaryButton")
        select_btn.setFixedWidth(100)
        select_btn.clicked.connect(self._accept_selected)
        button_row.addWidget(cancel_btn)
        button_row.addWidget(select_btn)
        layout.addLayout(button_row)

    def _accept_selected(self) -> None:
        item = self.list_widget.currentItem()
        if not item:
            return
        preset = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if preset:
            self.selected_preset = preset
            self.accept()


class HotkeyDialog(QtWidgets.QDialog):
    def __init__(self, preset: PresetGesture, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Assign Hotkey")
        self.setModal(True)
        self.setMinimumWidth(420)
        self.hotkey: str = ""
        self.mode: str = "static"

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QtWidgets.QLabel("Assign Hotkey")
        title.setObjectName("TitleLabel")
        layout.addWidget(title)

        gesture_label = QtWidgets.QLabel(f"Gesture: <b>{preset.name}</b>")
        gesture_label.setStyleSheet("color: #64748b; font-size: 13px;")
        layout.addWidget(gesture_label)

        hint_label = QtWidgets.QLabel("Press the key combination you want to use")
        hint_label.setStyleSheet("color: #64748b; font-size: 13px;")
        layout.addWidget(hint_label)

        self.key_edit = QtWidgets.QKeySequenceEdit()
        self.key_edit.setMinimumHeight(48)
        self.key_edit.keySequenceChanged.connect(self._update_hotkey)
        layout.addWidget(self.key_edit)

        mode_label = QtWidgets.QLabel("Collection Mode")
        mode_label.setStyleSheet("color: #64748b; font-size: 13px; margin-top: 8px;")
        layout.addWidget(mode_label)

        mode_row = QtWidgets.QHBoxLayout()
        mode_row.setSpacing(12)
        self.static_radio = QtWidgets.QRadioButton("Static")
        self.dynamic_radio = QtWidgets.QRadioButton("Dynamic")
        self.static_radio.setChecked(True)
        self.static_radio.toggled.connect(lambda checked: self._set_mode("static", checked))
        self.dynamic_radio.toggled.connect(lambda checked: self._set_mode("dynamic", checked))
        mode_row.addWidget(self.static_radio)
        mode_row.addWidget(self.dynamic_radio)
        mode_row.addStretch()
        layout.addLayout(mode_row)

        layout.addSpacing(8)

        button_row = QtWidgets.QHBoxLayout()
        button_row.addStretch()
        cancel_btn = QtWidgets.QPushButton("Cancel")
        cancel_btn.setFixedWidth(100)
        cancel_btn.clicked.connect(self.reject)
        self.confirm_btn = QtWidgets.QPushButton("Confirm")
        self.confirm_btn.setObjectName("PrimaryButton")
        self.confirm_btn.setFixedWidth(100)
        self.confirm_btn.setEnabled(False)
        self.confirm_btn.clicked.connect(self.accept)
        button_row.addWidget(cancel_btn)
        button_row.addWidget(self.confirm_btn)
        layout.addLayout(button_row)

    def _set_mode(self, mode: str, checked: bool) -> None:
        if checked:
            self.mode = mode

    def _update_hotkey(self, seq: QtGui.QKeySequence) -> None:
        self.hotkey = seq.toString(QtGui.QKeySequence.NativeText)
        self.confirm_btn.setEnabled(bool(self.hotkey))


class GestureRow(QtWidgets.QWidget):
    """Custom widget for a gesture row with better styling."""
    delete_clicked = QtCore.Signal(str)

    def __init__(self, label: str, hotkey: str, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.label = label
        self._hovered = False

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(16)

        preview = QtWidgets.QLabel(label.split("_")[0].capitalize())
        preview.setObjectName("GesturePreview")
        preview.setFixedSize(80, 80)
        preview.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(preview)

        hotkey_badge = QtWidgets.QLabel(hotkey or "Unset")
        hotkey_badge.setObjectName("HotkeyBadge")
        layout.addWidget(hotkey_badge)

        layout.addStretch()

        delete_btn = QtWidgets.QPushButton("Delete")
        delete_btn.setObjectName("DangerButton")
        delete_btn.setFixedHeight(32)
        delete_btn.clicked.connect(lambda: self.delete_clicked.emit(self.label))
        layout.addWidget(delete_btn)

    def enterEvent(self, event: QtCore.QEvent) -> None:
        self._hovered = True
        self.setStyleSheet("background: #f8fafc;")
        super().enterEvent(event)

    def leaveEvent(self, event: QtCore.QEvent) -> None:
        self._hovered = False
        self.setStyleSheet("")
        super().leaveEvent(event)


class EasyWindow(QtWidgets.QMainWindow):
    error_signal = QtCore.Signal(str)
    refresh_signal = QtCore.Signal()
    busy_signal = QtCore.Signal(bool)

    def __init__(self, workflow: GestureWorkflow, controller: CommandController) -> None:
        super().__init__()
        self.workflow = workflow
        self.controller = controller
        self.is_running = False
        self._busy = False
        self._poll_timer = QtCore.QTimer(self)
        self._poll_timer.setInterval(1000)
        self._poll_timer.timeout.connect(self._poll_last_detection)

        self.error_signal.connect(self._show_error)
        self.refresh_signal.connect(self._refresh_gestures)
        self.busy_signal.connect(self._set_busy)

        self._build_ui()
        self._refresh_gestures()

    def _build_ui(self) -> None:
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(900, 700)

        icon_path = Path("ui/assets/icons") / f"{APP_NAME.lower().replace(' ', '_')}.png"
        if icon_path.exists():
            self.setWindowIcon(QtGui.QIcon(str(icon_path)))

        central = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(0)

        header = QtWidgets.QHBoxLayout()
        header.setSpacing(16)
        title = QtWidgets.QLabel(APP_NAME)
        title.setObjectName("TitleLabel")
        header.addWidget(title)
        header.addStretch()

        self.run_btn = QtWidgets.QPushButton("Stopped")
        self.run_btn.setObjectName("RunButton")
        self.run_btn.setProperty("active", "false")
        self.run_btn.setFixedHeight(40)
        self.run_btn.clicked.connect(self._toggle_recognition)
        header.addWidget(self.run_btn)
        layout.addLayout(header)

        layout.addSpacing(24)

        self.error_banner = QtWidgets.QFrame()
        self.error_banner.setObjectName("Banner")
        self.error_banner.setProperty("variant", "error")
        self.error_label = QtWidgets.QLabel("")
        error_layout = QtWidgets.QHBoxLayout(self.error_banner)
        error_layout.setContentsMargins(16, 12, 16, 12)
        error_layout.addWidget(self.error_label)
        self.error_banner.hide()
        layout.addWidget(self.error_banner)

        self.detection_banner = QtWidgets.QFrame()
        self.detection_banner.setObjectName("Banner")
        self.detection_banner.setProperty("variant", "success")
        self.detection_label = QtWidgets.QLabel("")
        detection_layout = QtWidgets.QHBoxLayout(self.detection_banner)
        detection_layout.setContentsMargins(16, 12, 16, 12)
        detection_layout.addWidget(self.detection_label)
        self.detection_banner.hide()
        layout.addWidget(self.detection_banner)

        layout.addSpacing(16)

        self.stack = QtWidgets.QStackedWidget()

        self.main_page = QtWidgets.QWidget()
        main_layout = QtWidgets.QVBoxLayout(self.main_page)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        card = QtWidgets.QFrame()
        card.setObjectName("MainCard")
        card_layout = QtWidgets.QVBoxLayout(card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)

        self.empty_state = QtWidgets.QWidget()
        empty_layout = QtWidgets.QVBoxLayout(self.empty_state)
        empty_layout.setContentsMargins(48, 64, 48, 64)
        empty_icon = QtWidgets.QLabel("👋")
        empty_icon.setStyleSheet("font-size: 48px;")
        empty_icon.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        empty_text = QtWidgets.QLabel("No gestures tracked yet")
        empty_text.setStyleSheet("color: #94a3b8; font-size: 14px;")
        empty_text.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_icon)
        empty_layout.addSpacing(12)
        empty_layout.addWidget(empty_text)

        self.scroll_area = QtWidgets.QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        self.gesture_container = QtWidgets.QWidget()
        self.gesture_layout = QtWidgets.QVBoxLayout(self.gesture_container)
        self.gesture_layout.setContentsMargins(0, 0, 0, 0)
        self.gesture_layout.setSpacing(0)
        self.gesture_layout.addStretch()

        self.scroll_area.setWidget(self.gesture_container)

        card_layout.addWidget(self.empty_state)
        card_layout.addWidget(self.scroll_area)

        self.add_btn = QtWidgets.QPushButton("+ Add Gesture")
        self.add_btn.setObjectName("PrimaryButton")
        self.add_btn.setProperty("highlight", "false")
        self.add_btn.setFixedHeight(48)
        self.add_btn.clicked.connect(self._add_gesture_flow)
        card_layout.addWidget(self.add_btn)

        main_layout.addWidget(card)

        self.add_page = self._build_add_page()

        self.stack.addWidget(self.main_page)
        self.stack.addWidget(self.add_page)
        self.stack.setCurrentWidget(self.main_page)

        layout.addWidget(self.stack)
        layout.addStretch()
        self.setCentralWidget(central)

        status = self.statusBar()
        status.setSizeGripEnabled(False)
        build_stamp = QtWidgets.QLabel(_build_stamp())
        build_stamp.setObjectName("BuildStamp")
        status.addPermanentWidget(build_stamp, 1)

    def _build_add_page(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        title = QtWidgets.QLabel("Add Gesture")
        title.setObjectName("TitleLabel")
        layout.addWidget(title)

        hint = QtWidgets.QLabel("Choose a preset, set a hotkey, then collect samples.")
        hint.setStyleSheet("color: #64748b; font-size: 13px;")
        layout.addWidget(hint)

        self.add_preset_list = QtWidgets.QListWidget()
        self.add_preset_list.setSelectionMode(
            QtWidgets.QAbstractItemView.SingleSelection
        )
        for preset in PRESET_GESTURES:
            item = QtWidgets.QListWidgetItem(preset.name)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, preset)
            self.add_preset_list.addItem(item)
        self.add_preset_list.currentItemChanged.connect(self._update_add_preset)
        layout.addWidget(self.add_preset_list)

        hotkey_label = QtWidgets.QLabel("Hotkey")
        hotkey_label.setStyleSheet("color: #64748b; font-size: 13px;")
        layout.addWidget(hotkey_label)

        self.add_key_edit = QtWidgets.QKeySequenceEdit()
        self.add_key_edit.setMinimumHeight(48)
        self.add_key_edit.keySequenceChanged.connect(self._update_add_hotkey)
        layout.addWidget(self.add_key_edit)

        mode_label = QtWidgets.QLabel("Collection Mode")
        mode_label.setStyleSheet("color: #64748b; font-size: 13px;")
        layout.addWidget(mode_label)

        mode_row = QtWidgets.QHBoxLayout()
        mode_row.setSpacing(12)
        self.add_static_radio = QtWidgets.QRadioButton("Static")
        self.add_dynamic_radio = QtWidgets.QRadioButton("Dynamic")
        self.add_static_radio.setChecked(True)
        self.add_static_radio.toggled.connect(
            lambda checked: self._set_add_mode("static", checked)
        )
        self.add_dynamic_radio.toggled.connect(
            lambda checked: self._set_add_mode("dynamic", checked)
        )
        mode_row.addWidget(self.add_static_radio)
        mode_row.addWidget(self.add_dynamic_radio)
        mode_row.addStretch()
        layout.addLayout(mode_row)

        button_row = QtWidgets.QHBoxLayout()
        button_row.addStretch()
        cancel_btn = QtWidgets.QPushButton("Back")
        cancel_btn.setFixedWidth(100)
        cancel_btn.clicked.connect(self._show_main_page)
        self.add_confirm_btn = QtWidgets.QPushButton("Start Collection")
        self.add_confirm_btn.setObjectName("PrimaryButton")
        self.add_confirm_btn.setFixedWidth(160)
        self.add_confirm_btn.setEnabled(False)
        self.add_confirm_btn.clicked.connect(self._confirm_add_gesture)
        button_row.addWidget(cancel_btn)
        button_row.addWidget(self.add_confirm_btn)
        layout.addLayout(button_row)

        self._add_selected_preset: PresetGesture | None = None
        self._add_hotkey: str = ""
        self._add_mode: str = "static"

        return page

    def _show_error(self, message: str) -> None:
        if message:
            self.error_label.setText(message)
            self.error_banner.show()
        else:
            self.error_banner.hide()

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.add_btn.setEnabled(not busy)
        self.run_btn.setEnabled(not busy)

    def _toggle_recognition(self) -> None:
        if self.is_running:
            self.workflow.stop_recognition()
            self.is_running = False
            self._poll_timer.stop()
            self.detection_banner.hide()
            self._set_run_button_state(False)
            return

        if not self.workflow.dataset.list_gestures():
            self.error_signal.emit("Add a gesture before starting recognition.")
            self._nudge_add_button()
            return

        try:
            self.workflow.start_recognition(
                self.controller,
                confidence_threshold=0.6,
                stable_frames=5,
                show_window=False,
            )
            self.is_running = True
            self._poll_timer.start()
            self._set_run_button_state(True)
        except Exception as exc:
            self.error_signal.emit(str(exc))

    def _set_run_button_state(self, running: bool) -> None:
        self.run_btn.setText("Running" if running else "Stopped")
        self.run_btn.setProperty("active", "true" if running else "false")
        self.run_btn.style().unpolish(self.run_btn)
        self.run_btn.style().polish(self.run_btn)

    def _poll_last_detection(self) -> None:
        det = self.workflow.last_detection()
        if det and det.get("label") and det.get("label") != "NONE":
            label = det.get("label")
            conf = det.get("confidence")
            if conf is not None:
                text = f"Detected: <b>{label}</b> (conf {conf:.2f})"
            else:
                text = f"Detected: <b>{label}</b>"
            self.detection_label.setText(text)
            self.detection_banner.show()
        else:
            self.detection_banner.hide()

    def _refresh_gestures(self) -> None:
        while self.gesture_layout.count() > 1:
            item = self.gesture_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        items = self.workflow.dataset.list_gestures()

        for item in items:
            row = GestureRow(item["label"], item.get("hotkey") or "Unset")
            row.delete_clicked.connect(self._delete_gesture)
            self.gesture_layout.insertWidget(self.gesture_layout.count() - 1, row)

        has_items = bool(items)
        self.empty_state.setVisible(not has_items)
        self.scroll_area.setVisible(has_items)

    def _delete_gesture(self, label: str) -> None:
        confirm = QtWidgets.QMessageBox.question(
            self,
            "Delete Gesture",
            f"Delete '{label}' and retrain the model?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
        )
        if confirm != QtWidgets.QMessageBox.Yes:
            return
        try:
            self.workflow.dataset.remove_label(label)
            if self.workflow.dataset.X is not None:
                self.workflow.train_and_save()
            self._refresh_gestures()
        except Exception as exc:
            self._show_error(str(exc))

    def _add_gesture_flow(self) -> None:
        self._show_error("")
        self._reset_add_page()
        self.stack.setCurrentWidget(self.add_page)

    def _run_collection(self, preset: PresetGesture, hotkey: str, mode: str) -> None:
        self.busy_signal.emit(True)

        def _worker() -> None:
            try:
                if mode == "dynamic":
                    self.workflow.collect_dynamic(
                        preset.gesture_id,
                        repetitions=6,
                        sequence_length=25,
                        show_preview=False,
                    )
                else:
                    self.workflow.collect_static(
                        preset.gesture_id,
                        target_frames=60,
                        show_preview=False,
                    )
                self.workflow.dataset.set_hotkey(preset.gesture_id, hotkey)
                self.workflow.dataset.save()
                self.workflow.train_and_save()
                self.refresh_signal.emit()
                self._show_main_page()
            except Exception as exc:
                self.error_signal.emit(str(exc))
            finally:
                self.busy_signal.emit(False)

        thread = threading.Thread(target=_worker, name="GestureCollection", daemon=True)
        thread.start()

    def _show_main_page(self) -> None:
        self.stack.setCurrentWidget(self.main_page)

    def _update_add_preset(
        self,
        current: QtWidgets.QListWidgetItem | None,
        _previous: QtWidgets.QListWidgetItem | None,
    ) -> None:
        if current:
            self._add_selected_preset = current.data(QtCore.Qt.ItemDataRole.UserRole)
        else:
            self._add_selected_preset = None
        self._update_add_confirm_state()

    def _update_add_hotkey(self, seq: QtGui.QKeySequence) -> None:
        self._add_hotkey = seq.toString(QtGui.QKeySequence.NativeText)
        self._update_add_confirm_state()

    def _set_add_mode(self, mode: str, checked: bool) -> None:
        if checked:
            self._add_mode = mode

    def _update_add_confirm_state(self) -> None:
        can_confirm = bool(self._add_selected_preset and self._add_hotkey)
        self.add_confirm_btn.setEnabled(can_confirm)

    def _confirm_add_gesture(self) -> None:
        if not self._add_selected_preset or not self._add_hotkey:
            return
        self._run_collection(self._add_selected_preset, self._add_hotkey, self._add_mode)

    def _reset_add_page(self) -> None:
        self.add_preset_list.clearSelection()
        self.add_key_edit.clear()
        self.add_static_radio.setChecked(True)
        self._add_selected_preset = None
        self._add_hotkey = ""
        self._add_mode = "static"
        self._update_add_confirm_state()

    def _nudge_add_button(self) -> None:
        self.add_btn.setProperty("highlight", "true")
        self.add_btn.style().unpolish(self.add_btn)
        self.add_btn.style().polish(self.add_btn)
        QtCore.QTimer.singleShot(1500, self._clear_add_button_highlight)

    def _clear_add_button_highlight(self) -> None:
        self.add_btn.setProperty("highlight", "false")
        self.add_btn.style().unpolish(self.add_btn)
        self.add_btn.style().polish(self.add_btn)


class MainWindow:
    """Wrapper to launch the Qt app without requiring a QApplication at init."""

    def __init__(
        self,
        *,
        gesture_workflow: GestureWorkflow,
        controller: CommandController,
    ) -> None:
        self.gesture_workflow = gesture_workflow
        self.controller = controller
        self.is_open = False
        self._app: QtWidgets.QApplication | None = None
        self._window: EasyWindow | None = None

    def launch(self) -> None:
        """Start the Qt event loop (blocking)."""
        _ensure_qt_plugin_path()
        self._app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
        self._app.setStyle("Fusion")
        self._app.setStyleSheet(APP_STYLES)
        self._app.setApplicationName(APP_NAME)
        icon_path = Path("ui/assets/icons") / f"{APP_NAME.lower().replace(' ', '_')}.png"
        if icon_path.exists():
            self._app.setWindowIcon(QtGui.QIcon(str(icon_path)))

        self._window = EasyWindow(self.gesture_workflow, self.controller)
        self._window.show()
        self.is_open = True
        try:
            self._app.exec()
        finally:
            self.is_open = False

    def close(self) -> None:
        if self._window:
            self._window.close()
            self._window = None
        self.is_open = False
