from PySide6.QtCore import QObject, QTimer, Signal


TASK_STEPS = [
    ("Rest",          "Rest your hand in your lap or on the desk.",        5),
    ("Prepare",       "Raise your hand to writing position.",               3),
    ("Write",         "Write a letter or word in the air.",                10),
    ("Pause",         "Hold your hand still — pause mid-writing.",          3),
    ("Resume",        "Continue writing in the air.",                      10),
    ("Gesture",       "Make a non-writing gesture (e.g. wave or point).",   5),
    ("Return",        "Lower your hand and return to rest.",                3),
]


class TaskGuide(QObject):
    step_changed = Signal(int, str, str, int)   # index, name, instruction, total_seconds
    tick = Signal(int, int)                     # step_index, remaining_seconds
    completed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._step = 0
        self._remaining = 0
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._on_tick)

    def start(self):
        self._step = 0
        self._emit_step()
        self._timer.start()

    def skip(self):
        self._advance()

    def stop(self):
        self._timer.stop()

    def _emit_step(self):
        name, instruction, duration = TASK_STEPS[self._step]
        self._remaining = duration
        self.step_changed.emit(self._step, name, instruction, duration)
        self.tick.emit(self._step, self._remaining)

    def _on_tick(self):
        self._remaining -= 1
        self.tick.emit(self._step, self._remaining)
        if self._remaining <= 0:
            self._advance()

    def _advance(self):
        self._step += 1
        if self._step >= len(TASK_STEPS):
            self._timer.stop()
            self.completed.emit()
        else:
            self._emit_step()
