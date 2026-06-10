from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QSpinBox, QDialogButtonBox, QHeaderView,
)

from src.task_guide.guide import TASK_STEPS


class TaskDurationEditor(QDialog):
    def __init__(self, durations: list[int], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configure Task Durations")
        self.setMinimumWidth(380)
        self._spinboxes: list[QSpinBox] = []

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Set the duration (in seconds) for each task step:"))

        self._table = QTableWidget(len(TASK_STEPS), 3)
        self._table.setHorizontalHeaderLabels(["Step", "Instruction", "Duration (s)"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)

        for i, (name, instruction, _) in enumerate(TASK_STEPS):
            self._table.setItem(i, 0, QTableWidgetItem(name))
            self._table.setItem(i, 1, QTableWidgetItem(instruction))
            spin = QSpinBox()
            spin.setRange(1, 120)
            spin.setValue(durations[i] if i < len(durations) else 5)
            self._spinboxes.append(spin)
            self._table.setCellWidget(i, 2, spin)

        layout.addWidget(self._table)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_durations(self) -> list[int]:
        return [spin.value() for spin in self._spinboxes]
