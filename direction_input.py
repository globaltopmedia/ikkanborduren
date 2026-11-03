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

    def _point(self):
        return self.locale().decimalPoint()

    def _normal(self, text):
        # Accept both 63.5 and 63,5, whatever the system language is.
        point = self._point()
        return text.replace('.', point).replace(',', point)

    def validate(self, text, pos):
        return super().validate(self._normal(text), pos)

    def valueFromText(self, text):
        return super().valueFromText(self._normal(text))

    def keyPressEvent(self, event):
        if event.text() in ('.', ',') and event.text() != self._point():
            self.lineEdit().insert(self._point())
            event.accept()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.interpretText()
            self.enterPressed.emit()
            event.accept()
            return
        super().keyPressEvent(event)
