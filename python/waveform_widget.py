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
        self.view_start_time = 0.0  # Start time of the visible portion
        self.view_end_time = 0.0    # End time of the visible portion
        self.is_stereo = False
        self.auto_scroll = True      # Auto-scroll during playback

        self.setMinimumHeight(200)
        self.setMouseTracking(True)

    def set_waveform(self, data, duration):
        self.waveform_data = data
        self.duration = duration
        # Check if we have stereo data (4 values per sample)
        self.is_stereo = len(data) > 0 and len(data[0]) == 4

        # Initialize view to show full waveform
        if self.zoom_level == 1.0:
            self.view_start_time = 0.0
            self.view_end_time = duration
        else:
            # Keep current zoom level but ensure we're within bounds
            self.update_view_bounds()

        self.update()

    def update_view_bounds(self):
        """Update the view bounds based on zoom level and ensure they're valid"""
        if self.duration == 0:
            return

        visible_duration = self.duration / self.zoom_level

        # Ensure we don't go past the end
        if self.view_start_time + visible_duration > self.duration:
            self.view_start_time = max(0, self.duration - visible_duration)

        self.view_end_time = min(self.view_start_time + visible_duration, self.duration)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        width = self.width()
        height = self.height()

        # Background
        painter.fillRect(self.rect(), QColor(30, 30, 30))

        if not self.waveform_data or self.duration == 0:
            return

        # Calculate visible range
        visible_duration = self.view_end_time - self.view_start_time
        if visible_duration <= 0:
            return

        # Draw selection (if visible)
        if self.selection_start is not None and self.selection_end is not None:
            sel_start = min(self.selection_start, self.selection_end)
            sel_end = max(self.selection_start, self.selection_end)

            # Only draw if selection is visible
            if sel_end >= self.view_start_time and sel_start <= self.view_end_time:
                start_x = self.time_to_x(sel_start)
                end_x = self.time_to_x(sel_end)
                painter.fillRect(QRectF(start_x, 0, end_x - start_x, height),
                                 QColor(100, 150, 255, 80))

        # Calculate which samples to draw
        total_samples = len(self.waveform_data)
        if self.is_stereo:
            total_samples = len(self.waveform_data)  # Already have the right count

        start_fraction = self.view_start_time / self.duration if self.duration > 0 else 0
        end_fraction = self.view_end_time / self.duration if self.duration > 0 else 1

        start_sample = int(start_fraction * total_samples)
        end_sample = min(int(end_fraction * total_samples) + 1, total_samples)

        if start_sample >= end_sample:
            return

        samples_to_draw = end_sample - start_sample

        if self.is_stereo:
            # Draw stereo waveform
            channel_height = height / 2

            # Draw center lines for each channel
            painter.setPen(QPen(QColor(80, 80, 80), 1))
            painter.drawLine(0, int(channel_height / 2), width, int(channel_height / 2))
            painter.drawLine(0, int(channel_height + channel_height / 2),
                             width, int(channel_height + channel_height / 2))

            # Draw channel labels
            painter.setPen(QPen(QColor(150, 150, 150), 1))
            painter.drawText(5, 15, "L")
            painter.drawText(5, int(channel_height + 15), "R")

            # Draw waveforms
            painter.setPen(QPen(QColor(100, 200, 255), 1))

            for i in range(samples_to_draw):
                sample_idx = start_sample + i
                if sample_idx >= len(self.waveform_data):
                    break

                # Map sample position to x coordinate
                x = (i / samples_to_draw) * width

                # Get stereo data
                min_l, max_l, min_r, max_r = self.waveform_data[sample_idx]

                # Left channel
                y_min_l = (channel_height / 2) - (min_l * channel_height * 0.45)
                y_max_l = (channel_height / 2) - (max_l * channel_height * 0.45)
                painter.drawLine(QPointF(x, y_min_l), QPointF(x, y_max_l))

                # Right channel
                y_min_r = channel_height + (channel_height / 2) - (min_r * channel_height * 0.45)
                y_max_r = channel_height + (channel_height / 2) - (max_r * channel_height * 0.45)
                painter.drawLine(QPointF(x, y_min_r), QPointF(x, y_max_r))
        else:
            # Draw mono waveform
            center_y = height / 2

            # Draw center line
            painter.setPen(QPen(QColor(80, 80, 80), 1))
            painter.drawLine(0, int(center_y), width, int(center_y))

            # Draw waveform
            painter.setPen(QPen(QColor(100, 200, 255), 1))

            for i in range(samples_to_draw):
                sample_idx = start_sample + i
                if sample_idx >= len(self.waveform_data):
                    break

                # Map sample position to x coordinate
                x = (i / samples_to_draw) * width

                if len(self.waveform_data[sample_idx]) == 4:
                    # Stereo data, average it
                    min_l, max_l, min_r, max_r = self.waveform_data[sample_idx]
                    min_val = (min_l + min_r) / 2
                    max_val = (max_l + max_r) / 2
                else:
                    # Mono data
                    min_val, max_val = self.waveform_data[sample_idx]

                y_min = center_y - (min_val * center_y * 0.9)
                y_max = center_y - (max_val * center_y * 0.9)

                painter.drawLine(QPointF(x, y_min), QPointF(x, y_max))

        # Draw playback position (if visible)
        if (self.playback_position > 0 and
                self.playback_position >= self.view_start_time and
                self.playback_position <= self.view_end_time):
            x = self.time_to_x(self.playback_position)
            painter.setPen(QPen(QColor(255, 100, 100), 2))
            painter.drawLine(int(x), 0, int(x), height)

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

    def wheelEvent(self, event):
        """Handle mouse wheel for zooming"""
        # Get the position under the mouse
        mouse_time = self.x_to_time(event.position().x())

        # Zoom based on wheel direction
        delta = event.angleDelta().y()
        if delta > 0:
            # Zoom in
            old_zoom = self.zoom_level
            self.zoom_level = min(100.0, self.zoom_level * 1.2)

            if self.zoom_level != old_zoom and self.duration > 0:
                visible_duration = self.duration / self.zoom_level

                # Center on mouse position
                self.view_start_time = mouse_time - (event.position().x() / self.width()) * visible_duration
                self.view_start_time = max(0, self.view_start_time)
                self.view_end_time = min(self.duration, self.view_start_time + visible_duration)

                # Request waveform redraw
                parent = self.parent()
                if parent and hasattr(parent.parent(), 'update_waveform'):
                    parent.parent().update_waveform()
        elif delta < 0:
            # Zoom out
            old_zoom = self.zoom_level
            self.zoom_level = max(1.0, self.zoom_level / 1.2)

            if self.zoom_level != old_zoom and self.duration > 0:
                if self.zoom_level == 1.0:
                    self.view_start_time = 0.0
                    self.view_end_time = self.duration
                else:
                    visible_duration = self.duration / self.zoom_level

                    # Try to keep mouse position stable
                    self.view_start_time = mouse_time - (event.position().x() / self.width()) * visible_duration
                    self.view_start_time = max(0, self.view_start_time)
                    self.view_end_time = min(self.duration, self.view_start_time + visible_duration)

                # Request waveform redraw
                parent = self.parent()
                if parent and hasattr(parent.parent(), 'update_waveform'):
                    parent.parent().update_waveform()

        event.accept()

    def time_to_x(self, time):
        """Convert time to x coordinate in the current view"""
        if self.view_end_time == self.view_start_time:
            return 0
        fraction = (time - self.view_start_time) / (self.view_end_time - self.view_start_time)
        return fraction * self.width()

    def x_to_time(self, x):
        """Convert x coordinate to time in the current view"""
        if self.width() == 0:
            return self.view_start_time
        fraction = x / self.width()
        return self.view_start_time + fraction * (self.view_end_time - self.view_start_time)

    def get_selection(self):
        if self.selection_start is not None and self.selection_end is not None:
            if abs(self.selection_end - self.selection_start) > 0.001:  # Minimum selection size
                return (min(self.selection_start, self.selection_end),
                        max(self.selection_start, self.selection_end))
        return None

    def clear_selection(self):
        self.selection_start = None
        self.selection_end = None
        self.update()

    def set_playback_position(self, position):
        self.playback_position = position

        # Auto-scroll to follow playback if zoomed in
        if self.auto_scroll and self.zoom_level > 1.0:
            visible_duration = self.duration / self.zoom_level

            # Check if playback position is near the right edge (90% of visible area)
            if position > self.view_start_time + visible_duration * 0.9:
                # Scroll forward by half the visible duration
                new_start = position - visible_duration * 0.1
                self.view_start_time = max(0, min(new_start, self.duration - visible_duration))
                self.view_end_time = self.view_start_time + visible_duration

                # Request new waveform data for the new view
                parent = self.parent()
                if parent and hasattr(parent.parent(), 'update_waveform'):
                    parent.parent().update_waveform()
            # Check if playback position is before the view
            elif position < self.view_start_time:
                self.view_start_time = max(0, position)
                self.view_end_time = self.view_start_time + visible_duration

                # Request new waveform data for the new view
                parent = self.parent()
                if parent and hasattr(parent.parent(), 'update_waveform'):
                    parent.parent().update_waveform()

        self.update()

    def clear_playback_position(self):
        self.playback_position = 0.0
        self.update()

    def zoom_in(self):
        """Zoom in on the waveform"""
        old_zoom = self.zoom_level
        self.zoom_level = min(100.0, self.zoom_level * 1.5)

        if self.zoom_level != old_zoom and self.duration > 0:
            visible_duration = self.duration / self.zoom_level

            # Center on selection if exists, otherwise center on current view center
            selection = self.get_selection()
            if selection:
                sel_start, sel_end = selection
                center_time = (sel_start + sel_end) / 2
            else:
                # Center on current view center
                center_time = (self.view_start_time + self.view_end_time) / 2

            # Calculate new view bounds centered on the target
            self.view_start_time = center_time - visible_duration / 2
            self.view_start_time = max(0, self.view_start_time)
            self.view_end_time = min(self.duration, self.view_start_time + visible_duration)

            # Adjust if we hit the end
            if self.view_end_time >= self.duration:
                self.view_end_time = self.duration
                self.view_start_time = max(0, self.duration - visible_duration)

            # Request waveform redraw from parent
            parent = self.parent()
            if parent and hasattr(parent.parent(), 'update_waveform'):
                parent.parent().update_waveform()

    def zoom_out(self):
        """Zoom out on the waveform"""
        old_zoom = self.zoom_level
        self.zoom_level = max(1.0, self.zoom_level / 1.5)

        if self.zoom_level != old_zoom and self.duration > 0:
            if self.zoom_level == 1.0:
                # Show entire waveform
                self.view_start_time = 0.0
                self.view_end_time = self.duration
            else:
                visible_duration = self.duration / self.zoom_level

                # Try to keep the current center
                center_time = (self.view_start_time + self.view_end_time) / 2

                self.view_start_time = center_time - visible_duration / 2
                self.view_start_time = max(0, self.view_start_time)
                self.view_end_time = min(self.duration, self.view_start_time + visible_duration)

            # Request waveform redraw from parent
            parent = self.parent()
            if parent and hasattr(parent.parent(), 'update_waveform'):
                parent.parent().update_waveform()

    def zoom_to_selection(self):
        """Zoom to fit the current selection"""
        selection = self.get_selection()
        if selection and self.duration > 0:
            sel_start, sel_end = selection
            selection_duration = sel_end - sel_start

            # Add 10% padding on each side
            padding = selection_duration * 0.1
            self.view_start_time = max(0, sel_start - padding)
            self.view_end_time = min(self.duration, sel_end + padding)

            # Calculate zoom level from this
            visible_duration = self.view_end_time - self.view_start_time
            if visible_duration > 0:
                self.zoom_level = self.duration / visible_duration

            # Request waveform redraw
            parent = self.parent()
            if parent and hasattr(parent.parent(), 'update_waveform'):
                parent.parent().update_waveform()