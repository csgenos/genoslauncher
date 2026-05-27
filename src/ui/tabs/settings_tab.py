"""
Settings tab — RAM, JVM presets, Java, resolution, behavior.

JVM presets are shown as exclusive-select cards (Performance/LowLatency/ZGC/Fabric).
All settings auto-save to config.json via the config singleton.
"""

from __future__ import annotations

import subprocess

from PySide6.QtCore import QObject, QThread, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QPainter, QPainterPath
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QRadioButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..components.animated_button import OutlineButton, PrimaryButton
from ..components.themed_controls import GComboBox
from ..styles import COLORS as C, FONT, apply_theme, normalize_theme_mode
from ...core.config import config, APP_DIR
from ...core.java_manager import JVM_PRESETS, find_java_installations
from ...core.secure_store import get_secret, set_secret
from ..._version import __version__


# ---------------------------------------------------------------------------
# Feature 1: Performance Advisor worker
# ---------------------------------------------------------------------------

class _PerfAdvisorWorker(QObject):
    done = Signal(list)
    error = Signal(str)

    def run(self) -> None:
        try:
            advisories = self._analyse()
            self.done.emit(advisories)
        except Exception as exc:
            self.error.emit(str(exc))

    def _analyse(self) -> list[str]:
        try:
            import psutil
        except ImportError:
            return ["psutil not installed — install it to enable this feature."]

        advisories: list[str] = []
        vm = psutil.virtual_memory()
        total_mb = vm.total // (1024 * 1024)
        available_mb = vm.available // (1024 * 1024)
        ram_mb = int(config.get("ram_mb", 4096))

        if ram_mb > total_mb * 0.75:
            advisories.append(
                f"RAM allocation ({ram_mb // 1024} GB) exceeds 75 % of physical memory "
                f"({total_mb // 1024} GB) — reduce to avoid OS swapping."
            )

        if available_mb > 8192 and ram_mb < 4096:
            advisories.append(
                f"RAM is set to {ram_mb // 1024 if ram_mb >= 1024 else str(ram_mb) + ' MB'} "
                f"but your system has {available_mb // 1024} GB free — consider 4–6 GB for 1.18+."
            )

        jvm_preset = str(config.get("jvm_preset", "")).strip()
        jvm_args = str(config.get("jvm_args", "")).strip()

        if jvm_preset == "zgc" and total_mb < 8192:
            advisories.append(
                f"ZGC preset is selected but your system has only {total_mb // 1024} GB RAM total "
                "— Aikar's Flags will perform better."
            )

        if not jvm_preset and not jvm_args:
            advisories.append(
                "No JVM preset selected and no custom args set "
                "— select 'Performance (Aikar's Flags)' for a smoother experience."
            )

        instances = config.get("instances", [])
        selected_id = str(config.get("selected_instance_id", "")).strip()
        selected = next((i for i in instances if isinstance(i, dict) and i.get("id") == selected_id), None)
        if selected:
            mc_ver = str(selected.get("mc_version", "")).strip()
            parts = mc_ver.split(".")
            try:
                major = int(parts[1]) if len(parts) >= 2 else 0
                minor = int(parts[2]) if len(parts) >= 3 else 0
            except (ValueError, IndexError):
                major, minor = 0, 0
            if major >= 18 and ram_mb < 3072:
                advisories.append(
                    f"Instance '{selected.get('name', mc_ver)}' runs Minecraft {mc_ver} "
                    f"(1.18+) but only {ram_mb // 1024 if ram_mb >= 1024 else str(ram_mb) + ' MB'} RAM is allocated "
                    "— consider at least 3–4 GB."
                )
            if major < 13 and jvm_preset not in ("", "performance"):
                advisories.append(
                    f"Instance '{selected.get('name', mc_ver)}' runs Minecraft {mc_ver} "
                    "(pre-1.13) — legacy GC presets may perform better than modern flags."
                )

        return advisories


# ---------------------------------------------------------------------------
# Feature 1: Performance Advisor panel widget
# ---------------------------------------------------------------------------

class PerformanceAdvisorPanel(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        self._thread: QThread | None = None
        self._worker: _PerfAdvisorWorker | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        header_row = QHBoxLayout()
        title = QLabel("Performance Advisor")
        title.setStyleSheet(f"font-size: {FONT['md']}; font-weight: 700; color: {C['text_primary']};")
        header_row.addWidget(title)
        header_row.addStretch()
        self._run_btn = OutlineButton("Run Analysis")
        self._run_btn.setFixedHeight(32)
        self._run_btn.clicked.connect(self._run_analysis)
        header_row.addWidget(self._run_btn)
        layout.addLayout(header_row)

        self._result_lbl = QLabel("Click 'Run Analysis' to check your JVM and RAM settings.")
        self._result_lbl.setStyleSheet(f"font-size: {FONT['sm']}; color: {C['text_secondary']};")
        self._result_lbl.setWordWrap(True)
        layout.addWidget(self._result_lbl)

    def _run_analysis(self) -> None:
        self._run_btn.setEnabled(False)
        self._result_lbl.setStyleSheet(f"font-size: {FONT['sm']}; color: {C['text_secondary']};")
        self._result_lbl.setText("Analysing…")

        thread = QThread(self)
        worker = _PerfAdvisorWorker()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.done.connect(self._on_done)
        worker.error.connect(self._on_error)
        worker.done.connect(thread.quit)
        worker.error.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._on_thread_finished)
        self._thread = thread
        self._worker = worker
        thread.start()

    def _on_thread_finished(self) -> None:
        self._thread = None
        self._worker = None
        self._run_btn.setEnabled(True)

    def _on_done(self, advisories: list) -> None:
        if not advisories:
            self._result_lbl.setStyleSheet(f"font-size: {FONT['sm']}; color: {C['success']};")
            self._result_lbl.setText("No issues found.")
        else:
            self._result_lbl.setStyleSheet(f"font-size: {FONT['sm']}; color: {C['text_primary']};")
            self._result_lbl.setText("\n".join(f"• {a}" for a in advisories))

    def _on_error(self, msg: str) -> None:
        self._result_lbl.setStyleSheet(f"font-size: {FONT['sm']}; color: {C['danger']};")
        self._result_lbl.setText(f"Error: {msg}")


# ---------------------------------------------------------------------------
# Small helper widgets
# ---------------------------------------------------------------------------

class Divider(QFrame):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.HLine)
        self.setFixedHeight(1)
        self.setStyleSheet(f"background: {C['border']}; border: none;")


class SettingRow(QWidget):
    """Label-left + control-right layout row."""

    def __init__(self, label: str, control: QWidget, hint: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 6, 0, 6)
        layout.setSpacing(16)

        left = QVBoxLayout()
        left.setSpacing(2)
        lbl = QLabel(label)
        lbl.setStyleSheet(f"font-size: {FONT['md']}; font-weight: 600; color: {C['text_primary']};")
        left.addWidget(lbl)
        if hint:
            hint_lbl = QLabel(hint)
            hint_lbl.setStyleSheet(f"font-size: {FONT['xs']}; color: {C['text_tertiary']};")
            left.addWidget(hint_lbl)
        layout.addLayout(left, 1)
        layout.addWidget(control, 0)


class SectionTitle(QLabel):
    def __init__(self, text: str, parent=None) -> None:
        super().__init__(text, parent)
        self.setStyleSheet(f"font-size: {FONT['lg']}; font-weight: 700; color: {C['text_primary']}; margin-top: 4px;")


class _JavaDetectWorker(QObject):
    finished = Signal(list)

    def run(self) -> None:
        installs = find_java_installations()
        self.finished.emit(installs)


# ---------------------------------------------------------------------------
# RAM slider widget
# ---------------------------------------------------------------------------

class RamSlider(QWidget):
    """RAM allocation slider with live GB / MB badge."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 6, 0, 6)
        root.setSpacing(10)

        # Header row
        header = QHBoxLayout()
        lbl = QLabel("Allocated RAM")
        lbl.setStyleSheet(f"font-size: {FONT['md']}; font-weight: 600; color: {C['text_primary']};")
        header.addWidget(lbl)
        header.addStretch()
        self._badge = QLabel()
        self._badge.setStyleSheet(f"""
            background: {C["bg_secondary"]};
            border: 1px solid {C["border"]};
            border-radius: 6px;
            padding: 3px 10px;
            font-size: {FONT["sm"]};
            font-weight: 700;
            color: {C["text_primary"]};
        """)
        header.addWidget(self._badge)
        root.addLayout(header)

        hint = QLabel("4–8 GB recommended. More RAM helps with large modpacks; too much can hurt performance.")
        hint.setStyleSheet(f"font-size: {FONT['xs']}; color: {C['text_tertiary']};")
        hint.setWordWrap(True)
        root.addWidget(hint)

        self._slider = QSlider(Qt.Horizontal)
        self._slider.setMinimum(512)
        self._slider.setMaximum(32768)
        self._slider.setSingleStep(512)
        self._slider.setPageStep(1024)
        current = config.get("ram_mb", 4096)
        self._slider.setValue(current)
        self._slider.valueChanged.connect(self._on_changed)
        root.addWidget(self._slider)

        # Tick labels
        ticks = QHBoxLayout()
        for val in ["512 MB", "2 GB", "4 GB", "8 GB", "16 GB", "32 GB"]:
            t = QLabel(val)
            t.setStyleSheet(f"color: {C['text_tertiary']}; font-size: {FONT['xs']};")
            t.setAlignment(Qt.AlignCenter)
            ticks.addWidget(t)
        root.addLayout(ticks)

        self._update_badge(current)

    def _on_changed(self, value: int) -> None:
        snapped = round(value / 512) * 512
        if snapped != value:
            self._slider.setValue(snapped)
            return
        self._update_badge(snapped)
        config.set("ram_mb", snapped)

    def _update_badge(self, mb: int) -> None:
        self._badge.setText(f"{mb // 1024} GB" if mb >= 1024 else f"{mb} MB")


# ---------------------------------------------------------------------------
# JVM preset card
# ---------------------------------------------------------------------------

class JvmPresetCard(QFrame):
    """
    Selectable card for one JVM preset.
    Shows a radio indicator, name, and description.
    Selected state: accent-blue border + blue soft background.
    """

    selected = Signal(str)   # emits preset key

    def __init__(self, key: str, preset: dict, parent=None) -> None:
        super().__init__(parent)
        self._key = key
        self._selected = False

        self.setObjectName("JvmCard")
        self.setFixedHeight(82)
        self.setCursor(Qt.PointingHandCursor)
        self._update_style(False)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(14)

        self._radio = QRadioButton()
        self._radio.setStyleSheet("QRadioButton::indicator { width: 16px; height: 16px; }")
        self._radio.toggled.connect(lambda checked: self._on_toggled(checked))
        layout.addWidget(self._radio)

        text_col = QVBoxLayout()
        text_col.setSpacing(3)

        name_row = QHBoxLayout()
        name_lbl = QLabel(preset["name"])
        name_lbl.setStyleSheet(f"font-size: {FONT['md']}; font-weight: 700; color: {C['text_primary']};")
        name_row.addWidget(name_lbl)

        java_req = preset.get("java_min", 8)
        req_badge = QLabel(f"Java {java_req}+")
        req_badge.setStyleSheet(f"""
            background: {C["bg_tertiary"]};
            color: {C["text_secondary"]};
            border-radius: 4px;
            padding: 1px 7px;
            font-size: {FONT["xs"]};
            font-weight: 600;
        """)
        name_row.addWidget(req_badge)
        name_row.addStretch()
        text_col.addLayout(name_row)

        desc_lbl = QLabel(preset["description"])
        desc_lbl.setStyleSheet(f"font-size: {FONT['sm']}; color: {C['text_secondary']};")
        desc_lbl.setWordWrap(True)
        text_col.addWidget(desc_lbl)

        layout.addLayout(text_col, 1)

    def _update_style(self, selected: bool) -> None:
        if selected:
            self.setStyleSheet(f"""
                #JvmCard {{
                    background: {C["accent_blue_soft"]};
                    border: 1.5px solid {C["accent_blue"]};
                    border-radius: 10px;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                #JvmCard {{
                    background: {C["bg_primary"]};
                    border: 1px solid {C["border"]};
                    border-radius: 10px;
                }}
                #JvmCard:hover {{
                    border-color: {C["border_strong"]};
                }}
            """)

    def _on_toggled(self, checked: bool) -> None:
        self._selected = checked
        self._update_style(checked)
        if checked:
            self.selected.emit(self._key)

    def set_selected(self, selected: bool) -> None:
        self._radio.setChecked(selected)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._radio.setChecked(True)
        super().mousePressEvent(event)


# ---------------------------------------------------------------------------
# Settings Tab
# ---------------------------------------------------------------------------

class SettingsTab(QWidget):
    """Full settings panel."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._jvm_preset_group = QButtonGroup(self)
        self._jvm_preset_group.setExclusive(True)
        self._preset_cards: dict[str, JvmPresetCard] = {}
        self._debounce_timers: dict[str, QTimer] = {}
        self._pending_values: dict[str, object] = {}
        self._threads: list[QThread] = []
        self._workers: list[QObject] = []
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        content = QWidget()
        content.setStyleSheet(f"background: {C['bg_secondary']};")
        cl = QVBoxLayout(content)
        cl.setContentsMargins(40, 28, 40, 48)
        cl.setSpacing(0)

        # Page header
        title = QLabel("Settings")
        title.setStyleSheet(f"font-size: {FONT['2xl']}; font-weight: 800; color: {C['text_primary']};")
        cl.addWidget(title)
        sub = QLabel("Configure performance, Java, display, and launcher behavior.")
        sub.setStyleSheet(f"font-size: {FONT['sm']}; color: {C['text_secondary']}; margin-top: 4px;")
        cl.addWidget(sub)
        cl.addSpacing(28)

        # ── Performance ───────────────────────────────────────────────────────
        cl.addWidget(SectionTitle("Performance"))
        cl.addSpacing(12)

        perf_card = self._section_card()
        perf_layout = QVBoxLayout(perf_card)
        perf_layout.setContentsMargins(20, 16, 20, 16)
        perf_layout.setSpacing(8)

        perf_layout.addWidget(RamSlider())

        cl.addWidget(perf_card)
        cl.addSpacing(16)

        advisor_card = self._section_card()
        advisor_layout = QVBoxLayout(advisor_card)
        advisor_layout.setContentsMargins(20, 16, 20, 16)
        advisor_layout.setSpacing(0)
        advisor_layout.addWidget(PerformanceAdvisorPanel())
        cl.addWidget(advisor_card)
        cl.addSpacing(24)

        # ── JVM Configuration ────────────────────────────────────────────────
        cl.addWidget(SectionTitle("JVM Configuration"))
        cl.addSpacing(6)
        jvm_sub = QLabel("Choose a preset or enter custom flags. Presets are applied in addition to -Xmx/-Xms.")
        jvm_sub.setStyleSheet(f"font-size: {FONT['sm']}; color: {C['text_secondary']}; margin-bottom: 10px;")
        cl.addWidget(jvm_sub)
        cl.addSpacing(6)

        # Preset cards
        current_preset = config.get("jvm_preset", "performance")
        for key, preset in JVM_PRESETS.items():
            card = JvmPresetCard(key, preset, self)
            self._jvm_preset_group.addButton(card._radio)
            if key == current_preset:
                card.set_selected(True)
            card.selected.connect(self._on_preset_selected)
            self._preset_cards[key] = card
            cl.addWidget(card)
            cl.addSpacing(8)

        # Custom JVM args
        cl.addSpacing(6)
        custom_lbl = QLabel("Custom JVM Arguments")
        custom_lbl.setStyleSheet(f"font-size: {FONT['md']}; font-weight: 600; color: {C['text_primary']};")
        cl.addWidget(custom_lbl)
        custom_hint = QLabel("These are appended after the selected preset. Leave blank to use only the preset.")
        custom_hint.setStyleSheet(f"font-size: {FONT['xs']}; color: {C['text_tertiary']}; margin-bottom: 6px;")
        cl.addWidget(custom_hint)

        self._custom_jvm = QLineEdit()
        self._custom_jvm.setPlaceholderText("-XX:+UseStringDeduplication -Dfml.ignorePatchDiscrepancies=true …")
        self._custom_jvm.setText(config.get("jvm_args", ""))
        self._custom_jvm.setFixedHeight(40)
        self._custom_jvm.textChanged.connect(lambda t: self._debounced_set("jvm_args", t))
        cl.addWidget(self._custom_jvm)

        cl.addSpacing(28)

        # ── Java ─────────────────────────────────────────────────────────────
        cl.addWidget(SectionTitle("Java"))
        cl.addSpacing(12)

        java_card = self._section_card()
        java_layout = QVBoxLayout(java_card)
        java_layout.setContentsMargins(20, 16, 20, 16)
        java_layout.setSpacing(10)

        # Java path
        java_row = QWidget()
        java_row.setStyleSheet("background: transparent;")
        java_h = QHBoxLayout(java_row)
        java_h.setContentsMargins(0, 0, 0, 0)
        java_h.setSpacing(8)
        self._java_input = QLineEdit()
        self._java_input.setPlaceholderText("Auto-detect (leave blank)")
        self._java_input.setText(config.get("java_path", ""))
        self._java_input.setFixedHeight(38)
        self._java_input.textChanged.connect(lambda t: self._debounced_set("java_path", t))
        java_h.addWidget(self._java_input)
        browse_btn = OutlineButton("Browse")
        browse_btn.setFixedSize(80, 38)
        browse_btn.clicked.connect(self._browse_java)
        java_h.addWidget(browse_btn)
        test_java_btn = OutlineButton("Test")
        test_java_btn.setFixedSize(60, 38)
        test_java_btn.clicked.connect(self._test_java_path)
        java_h.addWidget(test_java_btn)
        java_layout.addWidget(SettingRow(
            "Java Executable",
            java_row,
            hint="Path to java.exe / java binary. Blank = auto-detect.",
        ))
        self._java_test_lbl = QLabel("")
        self._java_test_lbl.setStyleSheet(f"font-size: {FONT['xs']}; color: {C['text_secondary']};")
        self._java_test_lbl.setVisible(False)
        java_layout.addWidget(self._java_test_lbl)

        # Auto-detected installations
        self._java_detect_lbl = QLabel("Detecting Java installations…")
        self._java_detect_lbl.setStyleSheet(f"font-size: {FONT['xs']}; color: {C['text_tertiary']};")
        java_layout.addWidget(self._java_detect_lbl)

        self._java_combo = GComboBox()
        self._java_combo.setFixedHeight(36)
        self._java_combo.setEnabled(False)
        self._java_combo.currentIndexChanged.connect(self._on_java_selected)
        java_layout.addWidget(self._java_combo)

        manage_java_btn = OutlineButton("Manage Java Installations…")
        manage_java_btn.setFixedHeight(36)
        manage_java_btn.clicked.connect(self._open_java_manager)
        java_layout.addWidget(manage_java_btn)

        cl.addWidget(java_card)
        cl.addSpacing(24)

        # ── Window ──────────────────────────────────────────────────────────
        cl.addWidget(SectionTitle("Window & Display"))
        cl.addSpacing(12)

        win_card = self._section_card()
        win_layout = QVBoxLayout(win_card)
        win_layout.setContentsMargins(20, 16, 20, 16)
        win_layout.setSpacing(10)

        # Resolution
        res_widget = QWidget()
        res_widget.setStyleSheet("background: transparent;")
        res_h = QHBoxLayout(res_widget)
        res_h.setContentsMargins(0, 0, 0, 0)
        res_h.setSpacing(6)
        self._w_spin = QSpinBox()
        self._w_spin.setRange(800, 7680)
        self._w_spin.setValue(config.get("resolution_width", 1280))
        self._w_spin.setFixedHeight(36)
        self._w_spin.valueChanged.connect(lambda v: config.set("resolution_width", v))
        res_h.addWidget(self._w_spin)
        x_lbl = QLabel("×")
        x_lbl.setStyleSheet(f"color: {C['text_tertiary']}; font-size: {FONT['md']};")
        res_h.addWidget(x_lbl)
        self._h_spin = QSpinBox()
        self._h_spin.setRange(600, 4320)
        self._h_spin.setValue(config.get("resolution_height", 720))
        self._h_spin.setFixedHeight(36)
        self._h_spin.valueChanged.connect(lambda v: config.set("resolution_height", v))
        res_h.addWidget(self._h_spin)
        win_layout.addWidget(SettingRow("Game Resolution", res_widget, hint="Initial window size"))

        # Preset
        preset_combo = GComboBox()
        preset_combo.setFixedHeight(36)
        for label in ["Custom", "1280 × 720 (HD)", "1920 × 1080 (FHD)", "2560 × 1440 (QHD)", "3840 × 2160 (4K)"]:
            preset_combo.addItem(label)
        preset_combo.currentIndexChanged.connect(self._apply_res_preset)
        win_layout.addWidget(SettingRow("Resolution Preset", preset_combo))

        self._fullscreen = QCheckBox("Launch in fullscreen")
        self._fullscreen.setChecked(config.get("fullscreen", False))
        self._fullscreen.toggled.connect(lambda v: config.set("fullscreen", v))
        win_layout.addWidget(self._fullscreen)

        cl.addWidget(win_card)
        cl.addSpacing(24)

        # ── Launcher Behavior ────────────────────────────────────────────────
        cl.addWidget(SectionTitle("Launcher Behavior"))
        cl.addSpacing(12)

        behav_card = self._section_card()
        behav_layout = QVBoxLayout(behav_card)
        behav_layout.setContentsMargins(20, 16, 20, 16)
        behav_layout.setSpacing(8)

        self._close_on_launch = QCheckBox("Close launcher when Minecraft starts")
        self._close_on_launch.setChecked(config.get("close_on_launch", False))
        self._close_on_launch.toggled.connect(lambda v: config.set("close_on_launch", v))
        behav_layout.addWidget(self._close_on_launch)

        self._allow_online_token = QCheckBox("Allow online launch token in process arguments")
        self._allow_online_token.setChecked(config.get("allow_online_launch_token", False))
        self._allow_online_token.toggled.connect(lambda v: config.set("allow_online_launch_token", v))
        behav_layout.addWidget(self._allow_online_token)

        self._show_snapshots = QCheckBox("Show snapshot versions")
        self._show_snapshots.setChecked(config.get("show_snapshots", False))
        self._show_snapshots.toggled.connect(lambda v: config.set("show_snapshots", v))
        behav_layout.addWidget(self._show_snapshots)

        self._show_old = QCheckBox("Show legacy Alpha / Beta versions")
        self._show_old.setChecked(config.get("show_old_versions", False))
        self._show_old.toggled.connect(lambda v: config.set("show_old_versions", v))
        behav_layout.addWidget(self._show_old)

        self._modpack_update_policy = GComboBox()
        self._modpack_update_policy.setFixedHeight(34)
        self._modpack_update_policy.addItem("Manual", "manual")
        self._modpack_update_policy.addItem("Notify", "notify")
        self._modpack_update_policy.addItem("Auto on Launch", "auto-on-launch")
        current_policy = str(config.get("modpack_update_policy", "manual")).strip().lower()
        idx = max(0, self._modpack_update_policy.findData(current_policy))
        self._modpack_update_policy.setCurrentIndex(idx)
        self._modpack_update_policy.currentIndexChanged.connect(
            lambda i: config.set("modpack_update_policy", self._modpack_update_policy.itemData(i))
        )
        behav_layout.addWidget(
            SettingRow(
                "Modpack Updates",
                self._modpack_update_policy,
                hint="Manual: only when you click. Notify: auto-check and prompt. Auto on Launch: check and update automatically.",
            )
        )

        self._theme_mode = GComboBox()
        self._theme_mode.setFixedHeight(34)
        self._theme_mode.addItem("Light", "light")
        self._theme_mode.addItem("Dark", "dark")
        self._theme_mode.addItem("System", "system")
        current_theme = normalize_theme_mode(config.get("theme_mode", "dark" if config.get("dark_mode", False) else "light"))
        self._theme_mode.setCurrentIndex(max(0, self._theme_mode.findData(current_theme)))
        self._theme_mode.currentIndexChanged.connect(self._on_theme_mode_changed)
        behav_layout.addWidget(
            SettingRow(
                "Theme",
                self._theme_mode,
                hint="Light is the flagship white/slate look. Dark and System keep the same spacing and controls.",
            )
        )

        # Azure Client ID override (advanced users / self-builds)
        az_lbl = QLabel("Microsoft Authentication — Client ID Override")
        az_lbl.setStyleSheet(f"font-size: {FONT['md']}; font-weight: 600; color: {C['text_primary']}; margin-top: 8px;")
        behav_layout.addWidget(az_lbl)
        az_hint = QLabel(
            "Required for Microsoft sign-in. Paste your Azure App (public client) ID here.\n"
            "Blocked/legacy IDs are ignored automatically to prevent Microsoft consent errors."
        )
        az_hint.setStyleSheet(f"font-size: {FONT['xs']}; color: {C['text_tertiary']};")
        az_hint.setWordWrap(True)
        behav_layout.addWidget(az_hint)
        self._az_client_input = QLineEdit()
        self._az_client_input.setPlaceholderText("Enter Azure client ID (GUID)")
        self._az_client_input.setText(config.get("azure_client_id", ""))
        self._az_client_input.setFixedHeight(38)
        self._az_client_input.textChanged.connect(lambda t: self._debounced_set("azure_client_id", t.strip()))
        behav_layout.addWidget(self._az_client_input)

        # CurseForge API key
        cf_lbl = QLabel("CurseForge API Key")
        cf_lbl.setStyleSheet(f"font-size: {FONT['md']}; font-weight: 600; color: {C['text_primary']}; margin-top: 8px;")
        behav_layout.addWidget(cf_lbl)
        cf_hint = QLabel("Required for CurseForge mod/modpack search. Get a key at console.curseforge.com.")
        cf_hint.setStyleSheet(f"font-size: {FONT['xs']}; color: {C['text_tertiary']};")
        cf_hint.setWordWrap(True)
        behav_layout.addWidget(cf_hint)
        self._cf_key_input = QLineEdit()
        self._cf_key_input.setPlaceholderText("Enter CurseForge API key…")
        self._cf_key_input.setEchoMode(QLineEdit.Password)
        self._cf_key_input.setFixedHeight(38)
        self._cf_key_input.textChanged.connect(self._on_cf_key_changed)
        behav_layout.addWidget(self._cf_key_input)
        self._cf_key_error = QLabel("")
        self._cf_key_error.setStyleSheet(f"font-size: {FONT['xs']}; color: {C['danger']};")
        self._cf_key_error.setVisible(False)
        behav_layout.addWidget(self._cf_key_error)
        # Defer the keyring/fallback read off the critical widget-construction path
        QTimer.singleShot(0, self._load_cf_key)

        cl.addWidget(behav_card)
        cl.addSpacing(24)

        # ── Keyring Status ────────────────────────────────────────────────
        cl.addWidget(SectionTitle("Security & Storage"))
        cl.addSpacing(12)

        kr_card = self._section_card()
        kr_layout = QVBoxLayout(kr_card)
        kr_layout.setContentsMargins(20, 16, 20, 16)
        kr_layout.setSpacing(6)

        self._keyring_lbl = QLabel(self._get_keyring_status())
        self._keyring_lbl.setStyleSheet(f"font-size: {FONT['sm']}; color: {C['text_secondary']};")
        self._keyring_lbl.setWordWrap(True)
        kr_layout.addWidget(self._keyring_lbl)

        cl.addWidget(kr_card)
        cl.addSpacing(24)

        # ── Cloud Sync ────────────────────────────────────────────────────
        cl.addWidget(SectionTitle("Cloud Sync / Backup"))
        cl.addSpacing(12)

        sync_card = self._section_card()
        sync_layout = QVBoxLayout(sync_card)
        sync_layout.setContentsMargins(20, 16, 20, 16)
        sync_layout.setSpacing(8)
        sync_hint = QLabel(
            "Back up your instances to a local folder (e.g. Dropbox, OneDrive, NAS, or any directory). "
            "No cloud account required — just point to a synced folder."
        )
        sync_hint.setStyleSheet(f"font-size: {FONT['sm']}; color: {C['text_secondary']};")
        sync_hint.setWordWrap(True)
        sync_layout.addWidget(sync_hint)
        sync_btn = OutlineButton("Cloud Sync…")
        sync_btn.setFixedHeight(34)
        sync_btn.clicked.connect(self._open_cloud_sync)
        sync_layout.addWidget(sync_btn)
        cl.addWidget(sync_card)
        cl.addSpacing(24)

        # ── About ─────────────────────────────────────────────────────────
        cl.addWidget(SectionTitle("About"))
        cl.addSpacing(12)

        about_card = self._section_card()
        about_layout = QVBoxLayout(about_card)
        about_layout.setContentsMargins(20, 16, 20, 16)
        about_layout.setSpacing(8)

        ver_lbl = QLabel(f"GenosLauncher v{__version__}  ·  Open Source  ·  MIT License")
        ver_lbl.setStyleSheet(f"font-size: {FONT['sm']}; color: {C['text_secondary']};")
        about_layout.addWidget(ver_lbl)

        links_row = QHBoxLayout()
        _links = [
            ("GitHub",       "https://github.com/csgenos/genoslauncher"),
            ("Report a Bug", "https://github.com/csgenos/genoslauncher/issues/new"),
            ("Changelog",    "https://github.com/csgenos/genoslauncher/releases"),
        ]
        for txt, url in _links:
            btn = OutlineButton(txt)
            btn.setFixedHeight(32)
            btn.clicked.connect(lambda _=False, u=url: QDesktopServices.openUrl(QUrl(u)))
            links_row.addWidget(btn)
        links_row.addStretch()
        about_layout.addLayout(links_row)
        cl.addWidget(about_card)

        cl.addStretch()
        scroll.setWidget(content)
        root.addWidget(scroll)
        self._load_java_installs_async()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _section_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("SettingsCard")
        card.setStyleSheet(f"""
            #SettingsCard {{
                background: {C["bg_primary"]};
                border: 1px solid {C["border"]};
                border-radius: 12px;
            }}
        """)
        return card

    def _debounced_set(self, key: str, value: object, delay_ms: int = 600) -> None:
        self._pending_values[key] = value
        timer = self._debounce_timers.get(key)
        if timer is None:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(lambda k=key: config.set(k, self._pending_values.pop(k, "")))
            self._debounce_timers[key] = timer
        timer.start(delay_ms)

    def _load_cf_key(self) -> None:
        """Load the CurseForge API key from secure storage without blocking _build_ui."""
        self._cf_key_input.blockSignals(True)
        self._cf_key_input.setText(get_secret(APP_DIR, "curseforge_api_key"))
        self._cf_key_input.blockSignals(False)

    def _on_cf_key_changed(self, text: str) -> None:
        """Debounced save of the CurseForge API key to keyring/encrypted fallback."""
        _KEY = "curseforge_api_key"
        self._pending_values[_KEY] = text
        timer = self._debounce_timers.get(_KEY)
        if timer is None:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(self._save_cf_key)
            self._debounce_timers[_KEY] = timer
        timer.start(600)

    def _save_cf_key(self) -> None:
        value = self._pending_values.pop("curseforge_api_key", "")
        try:
            set_secret(APP_DIR, "curseforge_api_key", value)
            self._cf_key_error.setVisible(False)
        except Exception as exc:
            self._cf_key_error.setText(f"Failed to save key: {exc}")
            self._cf_key_error.setVisible(True)

    def _on_preset_selected(self, key: str) -> None:
        config.set("jvm_preset", key)

    def _browse_java(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Java Executable", "",
            "Executable (*.exe);;All Files (*)"
        )
        if path:
            self._java_input.setText(path)

    def _on_java_selected(self, index: int) -> None:
        path = self._java_combo.itemData(index)
        if path:
            self._java_input.setText(path)

    def _apply_res_preset(self, index: int) -> None:
        presets = [None, (1280,720), (1920,1080), (2560,1440), (3840,2160)]
        p = presets[index]
        if p:
            self._w_spin.setValue(p[0])
            self._h_spin.setValue(p[1])

    def _open_java_manager(self) -> None:
        from ..dialogs.java_manager_dialog import JavaManagerDialog
        dlg = JavaManagerDialog(self)
        dlg.exec()
        self._load_java_installs_async()

    def _on_theme_mode_changed(self, index: int) -> None:
        mode = self._theme_mode.itemData(index) or "light"
        config.update({"theme_mode": mode, "dark_mode": mode == "dark"})
        apply_theme(mode)
        # Force repaint of all widgets to pick up paintEvent color changes
        app = QApplication.instance()
        if app:
            for window in app.topLevelWidgets():
                if hasattr(window, "refresh_theme"):
                    window.refresh_theme()
            for widget in app.allWidgets():
                # Some Qt classes expose overloaded update methods that can fail
                # no-arg invocation via PySide; repaint is explicit and reliable.
                widget.repaint()

    def _load_java_installs_async(self) -> None:
        thread = QThread(self)
        worker = _JavaDetectWorker()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_java_installs_loaded)
        worker.finished.connect(thread.quit)
        self._threads.append(thread)
        self._workers.append(worker)
        thread.finished.connect(lambda: self._threads.remove(thread) if thread in self._threads else None)
        thread.finished.connect(lambda: self._workers.remove(worker) if worker in self._workers else None)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    def _on_java_installs_loaded(self, installs: list[dict]) -> None:
        self._java_combo.blockSignals(True)
        self._java_combo.clear()
        for j in installs[:8]:
            label = f"Java {j['major']}  ({j['path']})"
            self._java_combo.addItem(label, j["path"])
        self._java_combo.blockSignals(False)
        self._java_combo.setEnabled(bool(installs))
        self._java_detect_lbl.setText(
            f"Detected {len(installs)} Java installation(s):" if installs else "No Java installations detected."
        )

    def _test_java_path(self) -> None:
        path = self._java_input.text().strip() or "java"
        try:
            result = subprocess.run(
                [path, "-version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            output = (result.stderr or result.stdout or "").strip().splitlines()
            first_line = output[0] if output else "(no output)"
            self._java_test_lbl.setStyleSheet(f"font-size: {FONT['xs']}; color: {C['success']};")
            self._java_test_lbl.setText(f"OK: {first_line}")
        except FileNotFoundError:
            self._java_test_lbl.setStyleSheet(f"font-size: {FONT['xs']}; color: {C['danger']};")
            self._java_test_lbl.setText("Not found: java executable not found at this path.")
        except Exception as exc:
            self._java_test_lbl.setStyleSheet(f"font-size: {FONT['xs']}; color: {C['danger']};")
            self._java_test_lbl.setText(f"Error: {exc}")
        self._java_test_lbl.setVisible(True)

    def _open_cloud_sync(self) -> None:
        from ..dialogs.cloud_sync_dialog import CloudSyncDialog
        dlg = CloudSyncDialog(self)
        dlg.exec()

    def _get_keyring_status(self) -> str:
        try:
            import keyring
            backend = keyring.get_keyring()
            backend_name = type(backend).__name__
            if "fail" in backend_name.lower() or "null" in backend_name.lower():
                return (
                    f"Keyring backend: {backend_name}  ⚠  System keyring unavailable — "
                    "falling back to encrypted file store in app directory."
                )
            return f"Keyring backend: {backend_name}  ✓  Credentials stored in system keyring."
        except ImportError:
            return "keyring module not installed — credentials stored in encrypted file store."
        except Exception as exc:
            return f"Keyring check failed: {exc}"
