"""
Settings tab — RAM, JVM presets, Java, resolution, behavior.

JVM presets are shown as exclusive-select cards (Performance/LowLatency/ZGC/Fabric).
All settings auto-save to config.json via the config singleton.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QPainter, QPainterPath
from PySide6.QtWidgets import (
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

from ..styles import COLORS as C, FONT
from ..components.animated_button import OutlineButton, PrimaryButton
from ...core.config import config
from ...core.java_manager import JVM_PRESETS, find_java_installations


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
        self._custom_jvm.textChanged.connect(lambda t: config.set("jvm_args", t))
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
        self._java_input.textChanged.connect(lambda t: config.set("java_path", t))
        java_h.addWidget(self._java_input)
        browse_btn = OutlineButton("Browse")
        browse_btn.setFixedSize(80, 38)
        browse_btn.clicked.connect(self._browse_java)
        java_h.addWidget(browse_btn)
        java_layout.addWidget(SettingRow(
            "Java Executable",
            java_row,
            hint="Path to java.exe / java binary. Blank = auto-detect.",
        ))

        # Auto-detected installations
        installs = find_java_installations()
        if installs:
            detect_lbl = QLabel(f"Detected {len(installs)} Java installation(s):")
            detect_lbl.setStyleSheet(f"font-size: {FONT['xs']}; color: {C['text_tertiary']};")
            java_layout.addWidget(detect_lbl)

            self._java_combo = QComboBox()
            self._java_combo.setFixedHeight(36)
            for j in installs[:8]:
                label = f"Java {j['major']}  ({j['path']})"
                self._java_combo.addItem(label, j["path"])
            self._java_combo.currentIndexChanged.connect(self._on_java_selected)
            java_layout.addWidget(self._java_combo)

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
        preset_combo = QComboBox()
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

        self._show_snapshots = QCheckBox("Show snapshot versions")
        self._show_snapshots.setChecked(config.get("show_snapshots", False))
        self._show_snapshots.toggled.connect(lambda v: config.set("show_snapshots", v))
        behav_layout.addWidget(self._show_snapshots)

        self._show_old = QCheckBox("Show legacy Alpha / Beta versions")
        self._show_old.setChecked(config.get("show_old_versions", False))
        self._show_old.toggled.connect(lambda v: config.set("show_old_versions", v))
        behav_layout.addWidget(self._show_old)

        cl.addWidget(behav_card)
        cl.addSpacing(24)

        # ── About ─────────────────────────────────────────────────────────
        cl.addWidget(SectionTitle("About"))
        cl.addSpacing(12)

        about_card = self._section_card()
        about_layout = QVBoxLayout(about_card)
        about_layout.setContentsMargins(20, 16, 20, 16)
        about_layout.setSpacing(8)

        ver_lbl = QLabel("GenosLauncher v0.2.0  ·  Open Source  ·  MIT License")
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
