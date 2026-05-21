"""
Settings tab — RAM, resolution, Java path, theme, and more.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..styles import COLORS as C, FONT
from ..components.animated_button import GhostButton, AnimatedButton
from ...core.config import config


class SettingRow(QWidget):
    """A single settings row: label left, control right."""

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
            hint_lbl.setStyleSheet(f"font-size: {FONT['xs']}; color: {C['text_muted']};")
            left.addWidget(hint_lbl)
        layout.addLayout(left, 1)
        layout.addWidget(control, 0)


class RamSliderRow(QWidget):
    """RAM slider with live MB/GB display."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 8, 0, 8)
        root.setSpacing(8)

        header = QHBoxLayout()
        lbl = QLabel("Allocated RAM")
        lbl.setStyleSheet(f"font-size: {FONT['md']}; font-weight: 600; color: {C['text_primary']};")
        header.addWidget(lbl)
        header.addStretch()
        self._ram_display = QLabel()
        self._ram_display.setStyleSheet(f"""
            color: {C["accent_cyan"]};
            background: {C["accent_cyan"]}18;
            border: 1px solid {C["accent_cyan"]}33;
            border-radius: 6px;
            padding: 3px 10px;
            font-size: {FONT["sm"]};
            font-weight: 700;
        """)
        header.addWidget(self._ram_display)
        root.addLayout(header)

        hint = QLabel("More RAM improves performance but leaves less for your OS. 4–8 GB is recommended.")
        hint.setStyleSheet(f"font-size: {FONT['xs']}; color: {C['text_muted']};")
        root.addWidget(hint)

        self._slider = QSlider(Qt.Horizontal)
        self._slider.setMinimum(512)
        self._slider.setMaximum(32768)
        self._slider.setSingleStep(512)
        self._slider.setPageStep(1024)
        current_ram = config.get("ram_mb", 4096)
        self._slider.setValue(current_ram)
        self._slider.valueChanged.connect(self._on_changed)
        root.addWidget(self._slider)

        # Tick labels
        ticks = QHBoxLayout()
        for val in ["512 MB", "4 GB", "8 GB", "16 GB", "32 GB"]:
            t = QLabel(val)
            t.setStyleSheet(f"color: {C['text_muted']}; font-size: {FONT['xs']};")
            t.setAlignment(Qt.AlignCenter)
            ticks.addWidget(t)
        root.addLayout(ticks)

        self._update_display(current_ram)

    def _on_changed(self, value: int) -> None:
        # Snap to nearest 512
        snapped = round(value / 512) * 512
        if snapped != value:
            self._slider.setValue(snapped)
            return
        self._update_display(snapped)
        config.set("ram_mb", snapped)

    def _update_display(self, mb: int) -> None:
        if mb >= 1024:
            self._ram_display.setText(f"{mb // 1024} GB")
        else:
            self._ram_display.setText(f"{mb} MB")


class SettingsTab(QWidget):
    """Settings panel with grouped configuration options."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        content = QWidget()
        content.setStyleSheet(f"background-color: {C['bg_primary']};")
        cl = QVBoxLayout(content)
        cl.setContentsMargins(48, 32, 48, 48)
        cl.setSpacing(24)

        # Title
        title = QLabel("Settings")
        title.setStyleSheet(f"font-size: {FONT['2xl']}; font-weight: 800; color: {C['text_primary']};")
        cl.addWidget(title)

        # ---- Performance ----
        perf = QGroupBox("Performance")
        perf_layout = QVBoxLayout(perf)
        perf_layout.setSpacing(4)

        perf_layout.addWidget(RamSliderRow())

        # Java path
        java_row_widget = QWidget()
        java_row_widget.setStyleSheet("background: transparent;")
        java_h = QHBoxLayout(java_row_widget)
        java_h.setContentsMargins(0, 0, 0, 0)
        java_h.setSpacing(8)
        self._java_input = QLineEdit()
        self._java_input.setPlaceholderText("Leave blank to use system Java")
        self._java_input.setText(config.get("java_path", ""))
        self._java_input.setFixedHeight(38)
        self._java_input.textChanged.connect(lambda t: config.set("java_path", t))
        java_h.addWidget(self._java_input)
        browse_btn = GhostButton("Browse", accent=C["accent_cyan"])
        browse_btn.setFixedSize(80, 38)
        browse_btn.clicked.connect(self._browse_java)
        java_h.addWidget(browse_btn)

        perf_layout.addWidget(SettingRow(
            "Java Executable",
            java_row_widget,
            hint="Path to javaw.exe (Windows) or java binary",
        ))

        self._jvm_args = QLineEdit()
        self._jvm_args.setPlaceholderText("-XX:+UseG1GC -XX:+UnlockExperimentalVMOptions ...")
        self._jvm_args.setText(config.get("jvm_args", ""))
        self._jvm_args.setFixedHeight(38)
        self._jvm_args.textChanged.connect(lambda t: config.set("jvm_args", t))
        perf_layout.addWidget(SettingRow(
            "Extra JVM Arguments",
            self._jvm_args,
            hint="Advanced: additional flags passed to the JVM",
        ))

        cl.addWidget(perf)

        # ---- Window ----
        window_grp = QGroupBox("Window")
        window_layout = QVBoxLayout(window_grp)
        window_layout.setSpacing(4)

        res_widget = QWidget()
        res_widget.setStyleSheet("background: transparent;")
        res_h = QHBoxLayout(res_widget)
        res_h.setContentsMargins(0, 0, 0, 0)
        res_h.setSpacing(8)

        self._width_spin = QSpinBox()
        self._width_spin.setRange(800, 7680)
        self._width_spin.setValue(config.get("resolution_width", 1280))
        self._width_spin.setFixedHeight(38)
        self._width_spin.valueChanged.connect(lambda v: config.set("resolution_width", v))
        res_h.addWidget(self._width_spin)

        x_lbl = QLabel("×")
        x_lbl.setStyleSheet(f"color: {C['text_muted']}; font-size: {FONT['md']};")
        res_h.addWidget(x_lbl)

        self._height_spin = QSpinBox()
        self._height_spin.setRange(600, 4320)
        self._height_spin.setValue(config.get("resolution_height", 720))
        self._height_spin.setFixedHeight(38)
        self._height_spin.valueChanged.connect(lambda v: config.set("resolution_height", v))
        res_h.addWidget(self._height_spin)

        window_layout.addWidget(SettingRow("Game Resolution", res_widget, hint="Initial window size"))

        res_presets = QComboBox()
        res_presets.setFixedHeight(38)
        presets = ["Custom", "1280 × 720 (HD)", "1920 × 1080 (FHD)", "2560 × 1440 (QHD)", "3840 × 2160 (4K)"]
        res_presets.addItems(presets)
        res_presets.currentIndexChanged.connect(self._apply_resolution_preset)
        window_layout.addWidget(SettingRow("Quick Preset", res_presets))

        self._fullscreen_check = QCheckBox("Launch in fullscreen")
        self._fullscreen_check.setChecked(config.get("fullscreen", False))
        self._fullscreen_check.toggled.connect(lambda v: config.set("fullscreen", v))
        window_layout.addWidget(self._fullscreen_check)

        cl.addWidget(window_grp)

        # ---- Launcher Behavior ----
        behavior_grp = QGroupBox("Launcher Behavior")
        behavior_layout = QVBoxLayout(behavior_grp)
        behavior_layout.setSpacing(4)

        self._close_on_launch = QCheckBox("Close launcher when Minecraft starts")
        self._close_on_launch.setChecked(config.get("close_on_launch", False))
        self._close_on_launch.toggled.connect(lambda v: config.set("close_on_launch", v))
        behavior_layout.addWidget(self._close_on_launch)

        self._show_snapshots = QCheckBox("Show snapshot versions")
        self._show_snapshots.setChecked(config.get("show_snapshots", False))
        self._show_snapshots.toggled.connect(lambda v: config.set("show_snapshots", v))
        behavior_layout.addWidget(self._show_snapshots)

        self._show_old = QCheckBox("Show legacy alpha/beta versions")
        self._show_old.setChecked(config.get("show_old_versions", False))
        self._show_old.toggled.connect(lambda v: config.set("show_old_versions", v))
        behavior_layout.addWidget(self._show_old)

        cl.addWidget(behavior_grp)

        # ---- About ----
        about_grp = QGroupBox("About")
        about_layout = QVBoxLayout(about_grp)
        version_lbl = QLabel("GenosLauncher v0.1.0  ·  Open Source  ·  MIT License")
        version_lbl.setStyleSheet(f"color: {C['text_secondary']}; font-size: {FONT['sm']};")
        about_layout.addWidget(version_lbl)

        links_row = QHBoxLayout()
        for link_text, accent_col in [
            ("GitHub", C["accent_cyan"]),
            ("Report a Bug", C["danger"]),
            ("Discord", C["accent_purple"]),
        ]:
            btn = GhostButton(link_text, accent=accent_col)
            btn.setFixedHeight(34)
            links_row.addWidget(btn)
        links_row.addStretch()
        about_layout.addLayout(links_row)
        cl.addWidget(about_grp)

        # Save / Reset row
        actions_row = QHBoxLayout()
        actions_row.addStretch()
        reset_btn = GhostButton("Reset to Defaults", accent=C["danger"])
        reset_btn.setFixedHeight(38)
        actions_row.addWidget(reset_btn)
        save_btn = AnimatedButton(
            "Save Settings",
            color_start=C["accent_purple"],
            color_end=C["accent_cyan"],
            accent=C["accent_cyan"],
            text_color=C["bg_deep"],
        )
        save_btn.setFixedSize(150, 38)
        actions_row.addWidget(save_btn)
        cl.addLayout(actions_row)

        cl.addStretch()
        scroll.setWidget(content)
        root.addWidget(scroll)

    def _browse_java(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Java Executable", "", "Executable (*.exe);;All Files (*)"
        )
        if path:
            self._java_input.setText(path)

    def _apply_resolution_preset(self, index: int) -> None:
        presets = [
            None,
            (1280, 720),
            (1920, 1080),
            (2560, 1440),
            (3840, 2160),
        ]
        preset = presets[index]
        if preset:
            self._width_spin.setValue(preset[0])
            self._height_spin.setValue(preset[1])
