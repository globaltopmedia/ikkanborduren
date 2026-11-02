"""Angle entry commits typed text before applying stitches on Enter."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QDoubleSpinBox


class DirectionSpinBox(QDoubleSpinBox):
    enterPressed = Signal()

    def __init__(self, value=45., parent=None):
        super().__init__(parent)
        self.setRange(-360, 360)
        self.setDecimals(1)
        self.setSuffix('°')
        self.setValue(value)
        self.setKeyboardTracking(False)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.interpretText()
            self.enterPressed.emit()
            event.accept()
            return
        super().keyPressEvent(event)
