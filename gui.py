from __future__ import annotations

import os
import sys

from PySide6.QtCore import QObject, QSettings, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from obd_backend import DEFAULT_LIVE_PIDS, OBDBackend, OBDBackendError, available_ports

BAUD_RATES = ["Auto", "9600", "38400", "57600", "115200", "230400", "500000"]
HIGHLIGHT_PIDS = ["RPM", "SPEED", "COOLANT_TEMP", "THROTTLE_POS", "ENGINE_LOAD", "FUEL_LEVEL"]
NAV_ITEMS = ["Live Data", "Trouble Codes", "Freeze Frame", "Supported PIDs", "Settings"]

LIGHT_COLORS = dict(
    bg="#f2f3f5", surface="#ffffff", surface_alt="#f7f8fa", sidebar_bg="#ffffff",
    border="#dde1e6", text="#1c1e21", muted="#697077",
    accent="#2f6fed", accent_hover="#2657c4", accent_text="#ffffff", danger="#dc2626",
    badge_neutral_bg="#eef0f2", badge_neutral_text="#51565c",
    badge_success_bg="#e3f7ea", badge_success_text="#178a3f",
    badge_warning_bg="#fdf1de", badge_warning_text="#b45309",
)
DARK_COLORS = dict(
    bg="#16181c", surface="#1e2126", surface_alt="#23272d", sidebar_bg="#1b1d22",
    border="#2c3036", text="#e7e9ea", muted="#9aa1ab",
    accent="#3b82f6", accent_hover="#5b95f7", accent_text="#ffffff", danger="#f87171",
    badge_neutral_bg="#262a30", badge_neutral_text="#9aa1ab",
    badge_success_bg="#123420", badge_success_text="#3ddc78",
    badge_warning_bg="#3a2a10", badge_warning_text="#f5a623",
)


def _stylesheet(c):
    return f"""
QWidget {{ background: {c['bg']}; color: {c['text']}; font-size: 10pt; }}

QFrame[class="sidebar"] {{ background: {c['sidebar_bg']}; border-right: 1px solid {c['border']}; }}
QFrame[class="topbar"] {{ background: {c['bg']}; border-bottom: 1px solid {c['border']}; }}
QFrame[class="card"] {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 12px; }}

QLabel[class="brand"] {{ font-size: 14pt; font-weight: 700; padding: 4px 8px; }}
QLabel[class="stat-title"] {{ color: {c['muted']}; font-size: 9pt; font-weight: 700; }}
QLabel[class="stat-value"] {{ color: {c['text']}; font-size: 24pt; font-weight: 700; }}
QLabel[class="stat-unit"] {{ color: {c['muted']}; font-size: 11pt; padding-left: 2px; }}
QLabel[class="section-label"] {{ color: {c['muted']}; font-size: 9pt; font-weight: 700; padding-top: 6px; }}
QLabel[class="page-heading"] {{ font-size: 15pt; font-weight: 700; padding-bottom: 4px; }}

QPushButton {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 6px; padding: 6px 14px; }}
QPushButton:hover {{ border-color: {c['accent']}; }}
QPushButton:pressed {{ background: {c['border']}; }}
QPushButton:disabled {{ color: {c['muted']}; }}
QPushButton[accent="true"] {{
    background: {c['accent']}; border-color: {c['accent']}; color: {c['accent_text']}; font-weight: 600;
}}
QPushButton[accent="true"]:hover {{ background: {c['accent_hover']}; border-color: {c['accent_hover']}; }}
QPushButton[danger="true"] {{ color: {c['danger']}; border-color: {c['danger']}; }}
QPushButton[danger="true"]:hover {{ background: {c['danger']}; color: {c['accent_text']}; }}
QPushButton[class="nav-btn"] {{
    background: transparent; border: none; border-radius: 8px; color: {c['muted']};
    text-align: left; padding: 10px 12px; font-weight: 600;
}}
QPushButton[class="nav-btn"]:hover {{ background: {c['surface_alt']}; color: {c['text']}; }}
QPushButton[class="nav-btn"]:checked {{ background: {c['accent']}; color: {c['accent_text']}; }}

QComboBox, QLineEdit, QDoubleSpinBox {{
    background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 6px; padding: 4px 8px;
}}
QComboBox:focus, QLineEdit:focus, QDoubleSpinBox:focus {{ border-color: {c['accent']}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QCheckBox {{ spacing: 6px; }}

QLabel[status] {{ border-radius: 11px; padding: 4px 14px; font-weight: 700; }}
QLabel[status="neutral"] {{ background: {c['badge_neutral_bg']}; color: {c['badge_neutral_text']}; }}
QLabel[status="success"] {{ background: {c['badge_success_bg']}; color: {c['badge_success_text']}; }}
QLabel[status="warning"] {{ background: {c['badge_warning_bg']}; color: {c['badge_warning_text']}; }}

QTableWidget, QListWidget {{
    background: {c['surface']}; alternate-background-color: {c['surface_alt']};
    border: 1px solid {c['border']}; border-radius: 10px; gridline-color: transparent;
    selection-background-color: {c['accent']}; selection-color: {c['accent_text']};
}}
QHeaderView::section {{
    background: {c['surface']}; color: {c['muted']}; border: none;
    border-bottom: 1px solid {c['border']}; padding: 6px; font-weight: 600;
}}
QStatusBar {{ background: {c['bg']}; color: {c['muted']}; }}
QScrollBar:vertical {{ background: transparent; width: 10px; }}
QScrollBar::handle:vertical {{ background: {c['border']}; border-radius: 5px; min-height: 24px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
"""


LIGHT_QSS = _stylesheet(LIGHT_COLORS)
DARK_QSS = _stylesheet(DARK_COLORS)


class Worker(QObject):
    connected = Signal(bool, dict)
    disconnected = Signal()
    live_data = Signal(dict)
    dtcs = Signal(list)
    dtcs_cleared = Signal(bool)
    freeze_frame = Signal(dict)
    supported_pids = Signal(list)
    error = Signal(str)

    def __init__(self):
        super().__init__()
        self.backend = None
        self.timer = None

    @Slot(str, object, object, float)
    def connect_to(self, port, baud, protocol, timeout):
        try:
            self.backend = OBDBackend(portstr=port or None, baudrate=baud, protocol=protocol, timeout=timeout)
            self.connected.emit(self.backend.connect(), self.backend.connection_info())
        except Exception as exc:
            self.error.emit(f"Could not connect: {exc}")

    @Slot()
    def disconnect_adapter(self):
        self.stop_polling()
        if self.backend:
            self.backend.disconnect()
        self.backend = None
        self.disconnected.emit()

    @Slot()
    def start_polling(self):
        if not self.timer:
            self.timer = QTimer(self)
            self.timer.timeout.connect(self.poll)
        self.timer.start(1000)

    @Slot()
    def stop_polling(self):
        if self.timer:
            self.timer.stop()

    @Slot()
    def poll(self):
        if self._ready():
            self._run(lambda: self.live_data.emit(self.backend.read_live_data(DEFAULT_LIVE_PIDS)))

    @Slot()
    def fetch_dtcs(self):
        if self._ready():
            self._run(lambda: self.dtcs.emit(self.backend.get_dtcs()))

    @Slot()
    def clear_dtcs(self):
        if self._ready():
            self._run(lambda: self.dtcs_cleared.emit(self.backend.clear_dtcs()))

    @Slot()
    def fetch_freeze_frame(self):
        if self._ready():
            self._run(lambda: self.freeze_frame.emit(self.backend.get_freeze_frame()))

    @Slot()
    def fetch_supported_pids(self):
        if self._ready():
            self._run(lambda: self.supported_pids.emit(self.backend.list_supported_pids()))

    def _ready(self):
        if not self.backend:
            self.error.emit("Not connected.")
            return False
        return True

    def _run(self, action):
        try:
            action()
        except OBDBackendError as exc:
            self.error.emit(str(exc))


def _shadow(widget, blur=20, y=3, alpha=50):
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(blur)
    effect.setOffset(0, y)
    effect.setColor(QColor(0, 0, 0, alpha))
    widget.setGraphicsEffect(effect)


class MainWindow(QMainWindow):
    request_connect = Signal(str, object, object, float)
    request_disconnect = Signal()
    request_start_polling = Signal()
    request_stop_polling = Signal()
    request_snapshot = Signal()
    request_dtcs = Signal()
    request_clear_dtcs = Signal()
    request_freeze_frame = Signal()
    request_supported_pids = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Diagnostics")
        self.resize(1080, 700)
        self.connected = False
        self.live_rows = {}
        self.stat_labels = {}
        self.status_kind = "neutral"
        self.settings = QSettings("CarOBD", "CarOBD")

        self.thread = QThread(self)
        self.worker = Worker()
        self.worker.moveToThread(self.thread)
        self.thread.start()

        self._build_ui()
        self._wire()
        self.refresh_ports()
        self._set_connected_ui(False)

        dark = self.settings.value("dark_mode", False, type=bool)
        self.theme_btn.blockSignals(True)
        self.theme_btn.setChecked(dark)
        self.theme_btn.blockSignals(False)
        self.theme_btn.setText("Light Mode" if dark else "Dark Mode")
        self._apply_theme(dark)

    # ------------------------------------------------------------------ #
    # Layout
    # ------------------------------------------------------------------ #

    def _build_ui(self):
        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._sidebar())

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        content_layout.addWidget(self._top_bar())

        self.pages = QStackedWidget()
        self.pages.addWidget(self._live_page())
        self.pages.addWidget(self._dtc_page())
        self.pages.addWidget(self._freeze_page())
        self.pages.addWidget(self._pids_page())
        self.pages.addWidget(self._settings_page())

        pages_wrap = QWidget()
        pages_layout = QVBoxLayout(pages_wrap)
        pages_layout.setContentsMargins(24, 20, 24, 24)
        pages_layout.addWidget(self.pages)
        content_layout.addWidget(pages_wrap)

        root.addWidget(content, 1)
        self.setCentralWidget(central)
        self.statusBar().showMessage("Ready", 3000)

    def _sidebar(self):
        frame = QFrame()
        frame.setProperty("class", "sidebar")
        frame.setFixedWidth(210)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 20, 16, 16)
        layout.setSpacing(4)

        brand = QLabel("Diagnostics")
        brand.setProperty("class", "brand")
        layout.addWidget(brand)
        layout.addSpacing(16)

        self.nav_buttons = []
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        for i, label in enumerate(NAV_ITEMS):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setProperty("class", "nav-btn")
            self.nav_group.addButton(btn, i)
            layout.addWidget(btn)
            self.nav_buttons.append(btn)
        self.nav_buttons[0].setChecked(True)
        self.nav_group.idClicked.connect(lambda i: self.pages.setCurrentIndex(i))

        layout.addStretch()

        self.theme_btn = QPushButton("Dark Mode")
        self.theme_btn.setCheckable(True)
        self.theme_btn.setProperty("class", "nav-btn")
        self.theme_btn.toggled.connect(self.on_theme_toggled)
        layout.addWidget(self.theme_btn)

        return frame

    def _top_bar(self):
        frame = QFrame()
        frame.setProperty("class", "topbar")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(24, 16, 24, 16)

        self.port_combo = QComboBox()
        self.port_combo.setEditable(True)
        self.port_combo.setMinimumWidth(200)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setToolTip("Refresh ports")
        refresh_btn.clicked.connect(self.refresh_ports)

        self.connect_btn = QPushButton("Connect")
        self.connect_btn.setProperty("accent", True)
        self.connect_btn.clicked.connect(self.on_connect_clicked)

        self.status_badge = QLabel()

        layout.addWidget(QLabel("Port:"))
        layout.addWidget(self.port_combo)
        layout.addWidget(refresh_btn)
        layout.addSpacing(8)
        layout.addWidget(self.connect_btn)
        layout.addStretch()
        layout.addWidget(self.status_badge)

        self._set_status("Not connected", "neutral")
        return frame

    def _card(self):
        frame = QFrame()
        frame.setProperty("class", "card")
        _shadow(frame)
        return frame

    def _stat_card(self, name):
        frame = self._card()
        box = QVBoxLayout(frame)
        box.setContentsMargins(16, 14, 16, 16)

        title = QLabel(name.replace("_", " ").title())
        title.setProperty("class", "stat-title")
        box.addWidget(title)

        row = QHBoxLayout()
        value = QLabel("--")
        value.setProperty("class", "stat-value")
        unit = QLabel("")
        unit.setProperty("class", "stat-unit")
        unit.setAlignment(Qt.AlignBottom)
        row.addWidget(value)
        row.addWidget(unit)
        row.addStretch()
        box.addLayout(row)

        self.stat_labels[name] = (value, unit)
        return frame

    def _live_page(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        controls = QHBoxLayout()
        self.stream_checkbox = QCheckBox("Live streaming (1s)")
        self.stream_checkbox.setChecked(True)
        self.stream_checkbox.toggled.connect(self.on_stream_toggled)
        snapshot_btn = QPushButton("Snapshot")
        snapshot_btn.clicked.connect(self.request_snapshot.emit)
        controls.addWidget(self.stream_checkbox)
        controls.addWidget(snapshot_btn)
        controls.addStretch()
        layout.addLayout(controls)

        grid = QGridLayout()
        grid.setSpacing(14)
        for i, name in enumerate(HIGHLIGHT_PIDS):
            grid.addWidget(self._stat_card(name), i // 3, i % 3)
        layout.addLayout(grid)

        section_label = QLabel("ALL PARAMETERS")
        section_label.setProperty("class", "section-label")
        layout.addWidget(section_label)

        self.live_table = QTableWidget(len(DEFAULT_LIVE_PIDS), 4)
        self.live_table.setHorizontalHeaderLabels(["PID", "Description", "Value", "Unit"])
        self.live_table.verticalHeader().setVisible(False)
        self.live_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.live_table.setAlternatingRowColors(True)
        self.live_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        for row, name in enumerate(DEFAULT_LIVE_PIDS):
            self.live_rows[name] = row
            self.live_table.setItem(row, 0, QTableWidgetItem(name))
            self.live_table.setItem(row, 1, QTableWidgetItem(""))
            self.live_table.setItem(row, 2, QTableWidgetItem("--"))
            self.live_table.setItem(row, 3, QTableWidgetItem(""))
        layout.addWidget(self.live_table)

        return widget

    def _dtc_page(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.request_dtcs.emit)
        clear_btn = QPushButton("Clear Trouble Codes…")
        clear_btn.setProperty("danger", True)
        clear_btn.clicked.connect(self.on_clear_dtcs_clicked)

        controls = QHBoxLayout()
        controls.addWidget(refresh_btn)
        controls.addWidget(clear_btn)
        controls.addStretch()
        layout.addLayout(controls)

        self.dtc_table = QTableWidget(0, 2)
        self.dtc_table.setHorizontalHeaderLabels(["Code", "Description"])
        self.dtc_table.verticalHeader().setVisible(False)
        self.dtc_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.dtc_table.setAlternatingRowColors(True)
        self.dtc_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        layout.addWidget(self.dtc_table)

        return widget

    def _freeze_page(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.request_freeze_frame.emit)
        controls = QHBoxLayout()
        controls.addWidget(refresh_btn)
        controls.addStretch()
        layout.addLayout(controls)

        self.freeze_label = QLabel("No freeze frame stored.")
        layout.addWidget(self.freeze_label)

        self.freeze_table = QTableWidget(0, 3)
        self.freeze_table.setHorizontalHeaderLabels(["PID", "Value", "Unit"])
        self.freeze_table.verticalHeader().setVisible(False)
        self.freeze_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.freeze_table.setAlternatingRowColors(True)
        self.freeze_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        layout.addWidget(self.freeze_table)

        return widget

    def _pids_page(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.request_supported_pids.emit)
        controls = QHBoxLayout()
        controls.addWidget(refresh_btn)
        controls.addStretch()
        layout.addLayout(controls)

        self.pids_list = QListWidget()
        self.pids_list.setAlternatingRowColors(True)
        layout.addWidget(self.pids_list)

        return widget

    def _settings_page(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setAlignment(Qt.AlignTop)

        heading = QLabel("Connection Settings")
        heading.setProperty("class", "page-heading")
        layout.addWidget(heading)

        card = self._card()
        form = QVBoxLayout(card)
        form.setContentsMargins(20, 18, 20, 18)
        form.setSpacing(12)

        self.baud_combo = QComboBox()
        self.baud_combo.addItems(BAUD_RATES)
        self.protocol_edit = QLineEdit()
        self.protocol_edit.setPlaceholderText("auto")
        self.timeout_spin = QDoubleSpinBox()
        self.timeout_spin.setRange(1.0, 120.0)
        self.timeout_spin.setValue(30.0)

        for label_text, field in (
            ("Baud rate", self.baud_combo),
            ("Protocol", self.protocol_edit),
            ("Timeout (s)", self.timeout_spin),
        ):
            row = QHBoxLayout()
            label = QLabel(label_text)
            label.setFixedWidth(100)
            row.addWidget(label)
            row.addWidget(field)
            row.addStretch()
            form.addLayout(row)

        pair_btn = QPushButton("Pair Bluetooth Device…")
        pair_btn.clicked.connect(self.on_pair_bluetooth_clicked)
        form.addWidget(pair_btn)

        layout.addWidget(card)
        layout.addStretch()
        return widget

    def _wire(self):
        self.request_connect.connect(self.worker.connect_to)
        self.request_disconnect.connect(self.worker.disconnect_adapter)
        self.request_start_polling.connect(self.worker.start_polling)
        self.request_stop_polling.connect(self.worker.stop_polling)
        self.request_snapshot.connect(self.worker.poll)
        self.request_dtcs.connect(self.worker.fetch_dtcs)
        self.request_clear_dtcs.connect(self.worker.clear_dtcs)
        self.request_freeze_frame.connect(self.worker.fetch_freeze_frame)
        self.request_supported_pids.connect(self.worker.fetch_supported_pids)

        self.worker.connected.connect(self.on_connected)
        self.worker.disconnected.connect(self.on_disconnected)
        self.worker.live_data.connect(self.on_live_data)
        self.worker.dtcs.connect(self.on_dtcs)
        self.worker.dtcs_cleared.connect(self.on_dtcs_cleared)
        self.worker.freeze_frame.connect(self.on_freeze_frame)
        self.worker.supported_pids.connect(self.on_supported_pids)
        self.worker.error.connect(self.on_error)

    # ------------------------------------------------------------------ #
    # Handlers
    # ------------------------------------------------------------------ #

    def refresh_ports(self):
        current = self.port_combo.currentText()
        self.port_combo.clear()
        self.port_combo.addItem("Auto-detect")
        ports = available_ports()
        self.port_combo.addItems(ports)
        if current:
            self.port_combo.setCurrentText(current)
        self.statusBar().showMessage(f"Found {len(ports)} port(s)." if ports else "No serial ports detected.", 4000)

    def _set_status(self, text, kind="neutral"):
        self.status_kind = kind
        self.status_badge.setText(text)
        self.status_badge.setProperty("status", kind)
        self.status_badge.style().unpolish(self.status_badge)
        self.status_badge.style().polish(self.status_badge)

    def _style_connect_button(self, accent):
        self.connect_btn.setProperty("accent", accent)
        self.connect_btn.style().unpolish(self.connect_btn)
        self.connect_btn.style().polish(self.connect_btn)

    def _set_connected_ui(self, enabled):
        for i in range(self.pages.count() - 1):  # every page except Settings
            self.pages.widget(i).setEnabled(enabled)

    def on_theme_toggled(self, checked):
        self.theme_btn.setText("Light Mode" if checked else "Dark Mode")
        self.settings.setValue("dark_mode", checked)
        self._apply_theme(checked)

    def _apply_theme(self, dark):
        self.dark_mode = dark
        QApplication.instance().setStyleSheet(DARK_QSS if dark else LIGHT_QSS)

    def on_pair_bluetooth_clicked(self):
        if sys.platform == "win32":
            os.startfile("ms-settings:bluetooth")
            QMessageBox.information(
                self,
                "Pair Bluetooth adapter",
                "Pair your adapter (e.g. MUCAR BT200) in the Windows Bluetooth settings that just opened "
                "- PIN is usually 1234 or 0000.\n\n"
                "Once paired, Windows assigns it a COM port. Come back here and click Refresh Ports to find it.",
            )
        else:
            QMessageBox.information(
                self,
                "Pair Bluetooth adapter",
                "Pair the adapter with your system's Bluetooth settings, then bind it to a serial device, e.g.:\n\n"
                "sudo rfcomm bind 0 AA:BB:CC:DD:EE:FF\n\n"
                "Then click Refresh Ports and pick /dev/rfcomm0.",
            )

    def on_connect_clicked(self):
        if self.connected:
            self.request_stop_polling.emit()
            self.request_disconnect.emit()
            return

        port = self.port_combo.currentText().strip()
        port = "" if port in ("", "Auto-detect") else port
        baud = self.baud_combo.currentText()
        baud = None if baud == "Auto" else int(baud)
        protocol = self.protocol_edit.text().strip() or None
        timeout = self.timeout_spin.value()

        self.connect_btn.setEnabled(False)
        self.connect_btn.setText("Connecting…")
        self._set_status("Connecting…", "neutral")
        self.request_connect.emit(port, baud, protocol, timeout)

    def on_connected(self, car_connected, info):
        self.connected = True
        self.connect_btn.setEnabled(True)
        self.connect_btn.setText("Disconnect")
        self._style_connect_button(accent=False)
        self._set_connected_ui(True)

        if car_connected:
            self._set_status(f"Car Connected — {info['protocol_name']} on {info['port']}", "success")
        else:
            self._set_status(f"{info['status']} - car not responding yet", "warning")

        if self.stream_checkbox.isChecked():
            self.request_start_polling.emit()

    def on_disconnected(self):
        self.connected = False
        self.connect_btn.setEnabled(True)
        self.connect_btn.setText("Connect")
        self._style_connect_button(accent=True)
        self._set_status("Not connected", "neutral")
        self._set_connected_ui(False)

        for row in range(self.live_table.rowCount()):
            self.live_table.item(row, 1).setText("")
            self.live_table.item(row, 2).setText("--")
            self.live_table.item(row, 3).setText("")
        for value_label, unit_label in self.stat_labels.values():
            value_label.setText("--")
            unit_label.setText("")

    def on_stream_toggled(self, checked):
        if self.connected:
            (self.request_start_polling if checked else self.request_stop_polling).emit()

    def on_live_data(self, readings):
        for name, reading in readings.items():
            if not reading["supported"] or reading["value"] is None:
                value, unit = ("not supported" if not reading["supported"] else "no data"), ""
            else:
                value, unit = str(reading["value"]), reading["unit"] or ""

            row = self.live_rows.get(name)
            if row is not None:
                self.live_table.item(row, 1).setText(reading["description"] or "")
                self.live_table.item(row, 2).setText(value)
                self.live_table.item(row, 3).setText(unit)

            stat = self.stat_labels.get(name)
            if stat is not None:
                value_label, unit_label = stat
                value_label.setText(value)
                unit_label.setText(unit)

    def on_clear_dtcs_clicked(self):
        reply = QMessageBox.warning(
            self,
            "Clear trouble codes?",
            "This resets the check-engine light and erases the vehicle's readiness "
            "monitors and freeze frame data.\n\nThis cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.request_clear_dtcs.emit()

    def on_dtcs(self, codes):
        self.dtc_table.setRowCount(len(codes))
        for row, (code, description) in enumerate(codes):
            self.dtc_table.setItem(row, 0, QTableWidgetItem(code))
            self.dtc_table.setItem(row, 1, QTableWidgetItem(description or "(no description available)"))
        if not codes:
            self.statusBar().showMessage("No stored trouble codes.", 4000)

    def on_dtcs_cleared(self, ok):
        if ok:
            QMessageBox.information(self, "Trouble codes cleared", "Adapter acknowledged the clear command.")
        else:
            QMessageBox.warning(self, "Clear may have failed", "No response from the adapter.")
        self.request_dtcs.emit()
        self.request_freeze_frame.emit()

    def on_freeze_frame(self, frame):
        if frame["dtc"] is None:
            self.freeze_label.setText("No freeze frame stored.")
            self.freeze_table.setRowCount(0)
            return

        code, description = frame["dtc"]
        self.freeze_label.setText(f"Triggering DTC: {code} — {description or '(no description available)'}")

        params = frame["parameters"]
        self.freeze_table.setRowCount(len(params))
        for row, (name, reading) in enumerate(params.items()):
            value = reading["value"] if reading["value"] is not None else "no data"
            self.freeze_table.setItem(row, 0, QTableWidgetItem(name))
            self.freeze_table.setItem(row, 1, QTableWidgetItem(str(value)))
            self.freeze_table.setItem(row, 2, QTableWidgetItem(reading["unit"] or ""))

    def on_supported_pids(self, names):
        self.pids_list.clear()
        self.pids_list.addItems(names)

    def on_error(self, message):
        self.statusBar().showMessage(message, 6000)

    def closeEvent(self, event):
        self.request_stop_polling.emit()
        self.request_disconnect.emit()
        self.thread.quit()
        self.thread.wait(2000)
        super().closeEvent(event)
