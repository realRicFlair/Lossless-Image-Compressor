from PyQt5.QtWidgets import QSlider
from PyQt5.QtCore import QTimer, pyqtSignal, Qt

class DebouncedSlider(QSlider):
    # Custom signal emitted only after user stops moving the slider
    debouncedValueChanged = pyqtSignal(int)

    def __init__(self, orientation=Qt.Horizontal, parent=None, delay=300):
        super().__init__(orientation, parent)
        self._debounce_delay = delay  # ms
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._emit_debounced_value)
        self.valueChanged.connect(self._on_value_change)

    def _on_value_change(self, value):
        # Restart debounce timer every time slider value changes
        self._timer.start(self._debounce_delay)

    def _emit_debounced_value(self):
        # Emit the debounced signal when timer expires
        self.debouncedValueChanged.emit(self.value())

    def setDebounceDelay(self, delay_ms):
        """Change debounce duration dynamically"""
        self._debounce_delay = delay_ms
