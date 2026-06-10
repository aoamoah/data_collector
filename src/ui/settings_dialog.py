from PySide6.QtWidgets import (
    QDialog, QFormLayout, QComboBox, QDoubleSpinBox, QSpinBox,
    QCheckBox, QDialogButtonBox, QVBoxLayout, QLabel,
)

from src.config import AppConfig


class SettingsDialog(QDialog):
    def __init__(self, config: AppConfig, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Recording Settings")
        self.setMinimumWidth(340)
        self._config = config

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>Camera</b>"))

        form = QFormLayout()

        self._resolution = QComboBox()
        self._resolutions = [(640, 480), (1280, 720), (1920, 1080)]
        for w, h in self._resolutions:
            self._resolution.addItem(f"{w} × {h}", (w, h))
        current = config.resolution
        for i, r in enumerate(self._resolutions):
            if r == current:
                self._resolution.setCurrentIndex(i)
        form.addRow("Resolution", self._resolution)

        self._fps = QSpinBox()
        self._fps.setRange(10, 60)
        self._fps.setValue(config.fps)
        form.addRow("FPS", self._fps)

        layout.addLayout(form)
        layout.addSpacing(8)
        layout.addWidget(QLabel("<b>Processing</b>"))

        form2 = QFormLayout()
        self._threshold = QDoubleSpinBox()
        self._threshold.setRange(0.0, 1.0)
        self._threshold.setSingleStep(0.05)
        self._threshold.setDecimals(2)
        self._threshold.setValue(config.confidence_threshold)
        form2.addRow("Min confidence threshold", self._threshold)
        layout.addLayout(form2)

        layout.addSpacing(8)
        layout.addWidget(QLabel("<b>Task Guide</b>"))
        self._audio = QCheckBox("Enable audio cues (beep at step transitions)")
        self._audio.setChecked(config.audio_cues)
        layout.addWidget(self._audio)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _save(self):
        self._config.resolution = self._resolution.currentData()
        self._config.fps = self._fps.value()
        self._config.confidence_threshold = self._threshold.value()
        self._config.audio_cues = self._audio.isChecked()
        self.accept()

    def get_config(self) -> AppConfig:
        return self._config
