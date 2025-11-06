from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush


class WaveformWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.waveform_data = []
        self.duration = 0.0
        self.selection_start = None
        self.selection_end = None
        self.is_selecting = False
        self.playback_position = 0.0
        self.zoom_level = 1.0
        self.scroll_offset = 0.0

        self.setMinimumHeight(200)
        self.setMouseTracking(True)

    def set_waveform(self, data, duration):
        self.waveform_data = data
        self.duration = duration
        self.update()

    def paintEvent(self, event):
        if not self.waveform_data:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        width = self.width()
        height = self.height()
        center_y = height / 2

        # Background
        painter.fillRect(self.rect(), QColor(30, 30, 30))

        # Draw selection
        if self.selection_start is not None and self.selection_end is not None:
            start_x = self.time_to_x(min(self.selection_start, self.selection_end))
            end_x = self.time_to_x(max(self.selection_start, self.selection_end))
            painter.fillRect(QRectF(start_x, 0, end_x - start_x, height),
                             QColor(100, 150, 255, 80))

        # Draw waveform
        painter.setPen(QPen(QColor(100, 200, 255), 1))

        samples_to_draw = min(len(self.waveform_data), width)
        for i in range(samples_to_draw):
            if i >= len(self.waveform_data):
                break

            min_val, max_val = self.waveform_data[i]
            x = (i / len(self.waveform_data)) * width

            y_min = center_y - (min_val * center_y * 0.9)
            y_max = center_y - (max_val * center_y * 0.9)

            painter.drawLine(QPointF(x, y_min), QPointF(x, y_max))

        # Draw center line
        painter.setPen(QPen(QColor(80, 80, 80), 1))
        painter.drawLine(0, center_y, width, center_y)

        # Draw playback position
        if self.playback_position > 0:
            x = self.time_to_x(self.playback_position)
            painter.setPen(QPen(QColor(255, 100, 100), 2))
            painter.drawLine(x, 0, x, height)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_selecting = True
            time = self.x_to_time(event.position().x())
            self.selection_start = time
            self.selection_end = time
            self.update()

    def mouseMoveEvent(self, event):
        if self.is_selecting:
            time = self.x_to_time(event.position().x())
            self.selection_end = time
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_selecting = False

    def time_to_x(self, time):
        if self.duration == 0:
            return 0
        return (time / self.duration) * self.width()

    def x_to_time(self, x):
        return (x / self.width()) * self.duration

    def get_selection(self):
        if self.selection_start is not None and self.selection_end is not None:
            return (min(self.selection_start, self.selection_end),
                    max(self.selection_start, self.selection_end))
        return None

    def clear_selection(self):
        self.selection_start = None
        self.selection_end = None
        self.update()

    def set_playback_position(self, position):
        self.playback_position = position
        self.update()

    def clear_playback_position(self):
        self.playback_position = 0.0
        self.update()

    def zoom_in(self):
        self.zoom_level *= 1.5
        self.update()
        # Request waveform redraw from parent
        if self.parent():
            self.parent().update_waveform()

    def zoom_out(self):
        self.zoom_level = max(1.0, self.zoom_level / 1.5)
        self.update()
        # Request waveform redraw from parent
        if self.parent():
            self.parent().update_waveform()