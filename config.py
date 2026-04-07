import os
import json
from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
    QWidget, QFrame
)
from PyQt6.QtCore import Qt
from doogclips.gui.plugin_base import DoogPlugin

class PresetManagerPlugin(DoogPlugin):
    def __init__(self, parent=None):
        self.presets = {}
        self.storage_path = os.path.join(os.path.dirname(__file__), "presets_storage.json")
        
        super().__init__(parent)
        
        self.presets = self._load_presets()
        self._refresh_list()
        self.plugin_name = "Preset Manager"
        self.plugin_description = "Save and Autofill your favorite Styles, Voices, and Music."

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)

        hdr = QLabel("PRESET MANAGER")
        hdr.setObjectName("titleLabel")
        layout.addWidget(hdr)

        desc = QLabel("Save your current tab settings (Voice, Fonts, Backgrounds) as a one click preset.")
        desc.setObjectName("subtitleLabel")
        layout.addWidget(desc)

        list_box = QWidget()
        list_box.setObjectName("urlPanel")
        ll = QVBoxLayout(list_box)
        
        self.preset_list = QListWidget()
        self.preset_list.setObjectName("urlInput")
        self.preset_list.setStyleSheet("font-size: 14px; padding: 10px; border-radius: 8px;")
        self.preset_list.itemDoubleClicked.connect(self._apply_preset)
        ll.addWidget(self.preset_list)
        
        layout.addWidget(list_box, 1)

        ctrl_h = QHBoxLayout()
        self.apply_btn = QPushButton("Apply Selected")
        self.apply_btn.setObjectName("analyzeBtn")
        self.apply_btn.setFixedHeight(50)
        self.apply_btn.clicked.connect(self._apply_preset)
        
        self.delete_btn = QPushButton("Delete")
        self.delete_btn.setObjectName("openFolderBtn")
        self.delete_btn.setFixedHeight(50)
        self.delete_btn.setFixedWidth(100)
        self.delete_btn.clicked.connect(self._delete_preset)
        
        ctrl_h.addWidget(self.apply_btn, 1)
        ctrl_h.addWidget(self.delete_btn)
        layout.addLayout(ctrl_h)

        save_box = QWidget()
        save_box.setObjectName("urlPanel")
        sl = QHBoxLayout(save_box)
        
        self.name_input = QLineEdit()
        self.name_input.setObjectName("urlInput")
        self.name_input.setPlaceholderText("New Preset Name...")
        self.name_input.setFixedHeight(46)
        
        self.save_btn = QPushButton("Save Current State")
        self.save_btn.setObjectName("exportBtn")
        self.save_btn.setFixedHeight(46)
        self.save_btn.setFixedWidth(180)
        self.save_btn.clicked.connect(self._save_current_state)
        
        sl.addWidget(self.name_input, 1)
        sl.addWidget(self.save_btn)
        layout.addWidget(save_box)

    def _load_presets(self):
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, "r") as f:
                    return json.load(f)
            except: return {}
        return {}

    def _save_presets(self):
        try:
            with open(self.storage_path, "w") as f:
                json.dump(self.presets, f, indent=4)
        except: pass

    def _refresh_list(self):
        if not hasattr(self, 'preset_list'): return
        self.preset_list.clear()
        for name in sorted(self.presets.keys()):
            self.preset_list.addItem(name)

    def _save_current_state(self):
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Error", "Give your preset a name first!")
            return

        mw = self.parent_win
        if not mw: return

        state = {}
        widgets = [
            "font_family_combo", "style_combo", "color_combo", "color2_combo",
            "font_spin", "stroke_spin", "words_combo", "glow_chk", "emoji_chk",
            "pbar_chk", "slide_chk", "spk1_combo", "spk2_combo", "spk3_combo", "spk4_combo",
            "red_voice", "red_speed", "red_whisper_model", "red_bg_combo", "red_bgm_combo",
            "red_bgm_vol", "red_dropdown_chk", "red_fast_mode_chk", "red_gpu_chk",
            "bgm_clip_combo", "clip_bgm_vol", "min_dur_sp", "max_dur_sp",
            "whisper_model_combo", "max_clips_sp", "gameplay_chk", "facecam_chk",
            "gpu_chk", "track_strength_sp", "bg_clip_combo",
            "red_bgm_custom", "red_bg_custom", "red_sub", "red_title", "red_story",
            "bg_clip_custom", "bgm_clip_custom"
        ]

        from PyQt6.QtWidgets import QComboBox, QSpinBox, QCheckBox, QSlider, QLineEdit, QTextEdit
        for w_name in widgets:
            if hasattr(mw, w_name):
                widget = getattr(mw, w_name)
                if isinstance(widget, QComboBox): state[w_name] = widget.currentText()
                elif isinstance(widget, QSpinBox): state[w_name] = widget.value()
                elif isinstance(widget, QCheckBox): state[w_name] = widget.isChecked()
                elif isinstance(widget, QSlider): state[w_name] = widget.value()
                elif isinstance(widget, QLineEdit): state[w_name] = widget.text()
                elif isinstance(widget, QTextEdit): state[w_name] = widget.toPlainText()

        self.presets[name] = state
        self._save_presets()
        self._refresh_list()
        self.name_input.clear()
        QMessageBox.information(self, "Success", f"Preset '{name}' saved!")

    def _apply_preset(self):
        item = self.preset_list.currentItem()
        if not item: return
        
        name = item.text()
        state = self.presets.get(name, {})
        mw = self.parent_win
        if not mw: return

        from PyQt6.QtWidgets import QComboBox, QSpinBox, QCheckBox, QSlider, QLineEdit, QTextEdit
        for w_name, val in state.items():
            if hasattr(mw, w_name):
                widget = getattr(mw, w_name)
                try:
                    if isinstance(widget, QComboBox):
                        idx = widget.findText(val)
                        if idx >= 0: widget.setCurrentIndex(idx)
                    elif isinstance(widget, QSpinBox): widget.setValue(val)
                    elif isinstance(widget, QCheckBox): widget.setChecked(val)
                    elif isinstance(widget, QSlider): widget.setValue(val)
                    elif isinstance(widget, QLineEdit): widget.setText(val)
                    elif isinstance(widget, QTextEdit): widget.setPlainText(val)
                except: pass

        QMessageBox.information(self, "Applied", f"Preset '{name}' has been autofilled!")

    def _delete_preset(self):
        item = self.preset_list.currentItem()
        if not item: return
        
        name = item.text()
        if QMessageBox.question(self, "Delete?", f"Delete preset '{name}'?") == QMessageBox.StandardButton.Yes:
            if name in self.presets:
                del self.presets[name]
                self._save_presets()
                self._refresh_list()
