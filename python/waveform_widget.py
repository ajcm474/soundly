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
        self.channels = 2
        self.auto_scroll = True      # Auto-scroll during playback

        self.setMinimumHeight(200)
        self.setMouseTracking(True)

    def format_time(self, time_seconds):
        """Format time in human-readable format"""
        hours = int(time_seconds // 3600)
        minutes = int((time_seconds % 3600) // 60)
        seconds = time_seconds % 60

        parts = []
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")

        # Format seconds based on zoom level
        if self.zoom_level > 100:
            # Show milliseconds when zoomed in
            parts.append(f"{seconds:.3f}s")
        elif self.zoom_level > 10:
            parts.append(f"{seconds:.2f}s")
        elif self.zoom_level > 1:
            parts.append(f"{seconds:.1f}s")
        else:
            parts.append(f"{int(seconds)}s")

        return ''.join(parts) if parts else "0s"

    def set_waveform(self, data, duration, channels=None):
        self.waveform_data = data
        self.duration = duration
        self.channels = channels if channels else 2

        # Determine if stereo based on actual channel count
        self.is_stereo = self.channels == 2

        # Initialize view to show full waveform if at default zoom
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

        # Reserve space for time ruler
        ruler_height = 30
        waveform_height = height - ruler_height

        # Background
        painter.fillRect(self.rect(), QColor(30, 30, 30))

        if not self.waveform_data or self.duration == 0:
            return

        # Draw time ruler
        self.draw_time_ruler(painter, width, ruler_height)

        # Save state before translating
        painter.save()
        painter.translate(0, ruler_height)

        # Calculate visible range
        visible_duration = self.view_end_time - self.view_start_time
        if visible_duration <= 0:
            painter.restore()  # Restore before returning
            return

        # Draw selection (if visible)
        if self.selection_start is not None and self.selection_end is not None:
            sel_start = min(self.selection_start, self.selection_end)
            sel_end = max(self.selection_start, self.selection_end)

            # Only draw if selection is visible
            if sel_end >= self.view_start_time and sel_start <= self.view_end_time:
                start_x = self.time_to_x(sel_start)
                end_x = self.time_to_x(sel_end)
                painter.fillRect(QRectF(start_x, 0, end_x - start_x, waveform_height),
                                 QColor(100, 150, 255, 80))

        # Draw waveform
        total_samples = len(self.waveform_data)
        if total_samples == 0:
            painter.restore()
            return

        if self.is_stereo and self.channels == 2:
            # Draw stereo waveform
            channel_height = waveform_height / 2

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

            for i in range(total_samples):
                if i >= len(self.waveform_data):
                    break

                # When zoomed in to individual samples, we have more data points than pixels
                # Map sample position to x coordinate based on the number of samples
                if total_samples > width:
                    # Individual sample mode: map samples across the width
                    x = (i / total_samples) * width
                else:
                    # Normal mode: one data point per pixel
                    x = (i / total_samples) * width

                # Get stereo data
                min_l, max_l, min_r, max_r = self.waveform_data[i]

                # Left channel
                y_min_l = (channel_height / 2) - (min_l * channel_height * 0.45)
                y_max_l = (channel_height / 2) - (max_l * channel_height * 0.45)
                painter.drawLine(QPointF(x, y_min_l), QPointF(x, y_max_l))

                # Right channel
                y_min_r = channel_height + (channel_height / 2) - (min_r * channel_height * 0.45)
                y_max_r = channel_height + (channel_height / 2) - (max_r * channel_height * 0.45)
                painter.drawLine(QPointF(x, y_min_r), QPointF(x, y_max_r))
        else:
            # Draw mono waveform - single channel in center
            center_y = waveform_height / 2

            # Draw center line
            painter.setPen(QPen(QColor(80, 80, 80), 1))
            painter.drawLine(0, int(center_y), width, int(center_y))

            # Draw waveform
            painter.setPen(QPen(QColor(100, 200, 255), 1))

            for i in range(total_samples):
                if i >= len(self.waveform_data):
                    break

                # Map sample position to x coordinate
                if total_samples > width:
                    # Individual sample mode: map samples across the width
                    x = (i / total_samples) * width
                else:
                    # Normal mode: one data point per pixel
                    x = (i / total_samples) * width

                # Get mono data (from first two values)
                min_val, max_val = self.waveform_data[i][:2]

                y_min = center_y - (min_val * center_y * 0.9)
                y_max = center_y - (max_val * center_y * 0.9)

                painter.drawLine(QPointF(x, y_min), QPointF(x, y_max))

        # Restore painter state
        painter.restore()

        # Draw playback position (if visible) - after restoring so it's not translated
        if (self.playback_position > 0 and
                self.playback_position >= self.view_start_time and
                self.playback_position <= self.view_end_time):
            x = self.time_to_x(self.playback_position)
            painter.setPen(QPen(QColor(255, 100, 100), 2))
            painter.drawLine(int(x), 0, int(x), height)

    def draw_time_ruler(self, painter, width, ruler_height):
        """Draw time ruler at the top of the widget"""
        # Background for ruler
        painter.fillRect(0, 0, width, ruler_height, QColor(40, 40, 40))

        # Border line
        painter.setPen(QPen(QColor(80, 80, 80), 1))
        painter.drawLine(0, ruler_height - 1, width, ruler_height - 1)

        # Calculate appropriate time interval based on zoom
        visible_duration = self.view_end_time - self.view_start_time

        # Determine grid interval
        intervals = [
            (0.001, "%.3fs"),   # milliseconds
            (0.01, "%.2fs"),    # 10ms
            (0.1, "%.1fs"),     # 100ms
            (1.0, "%.0fs"),     # seconds
            (5.0, "%.0fs"),     # 5 seconds
            (10.0, "%.0fs"),    # 10 seconds
            (30.0, "%.0fs"),    # 30 seconds
            (60.0, "%d:%02d"),  # minutes
            (300.0, "%d:%02d"), # 5 minutes
            (600.0, "%d:%02d"), # 10 minutes
        ]

        # Find appropriate interval (aim for 50-200 pixels between marks)
        target_spacing = 100
        time_per_pixel = visible_duration / width
        ideal_interval = target_spacing * time_per_pixel

        interval = intervals[0][0]
        format_str = intervals[0][1]

        for int_val, fmt in intervals:
            if int_val >= ideal_interval * 0.5:
                interval = int_val
                format_str = fmt
                break

        # Draw time marks
        painter.setPen(QPen(QColor(200, 200, 200), 1))
        font = painter.font()
        font.setPointSize(8)
        painter.setFont(font)

        # Start from the first interval mark after view_start_time
        first_mark = (self.view_start_time // interval) * interval
        if first_mark < self.view_start_time:
            first_mark += interval

        current_time = first_mark
        while current_time <= self.view_end_time:
            x = self.time_to_x(current_time)

            # Draw tick mark
            painter.drawLine(int(x), ruler_height - 10, int(x), ruler_height - 1)

            # Format time label using the new formatter
            label = self.format_time(current_time)

            # Draw label
            rect = QRectF(x - 40, 2, 80, ruler_height - 12)
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, label)

            current_time += interval

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # Ignore clicks in the ruler area
            if event.position().y() < 30:
                return

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

        # Calculate maximum zoom
        max_zoom = 10000.0
        if hasattr(self.parent().parent(), 'engine'):
            try:
                sample_rate = self.parent().parent().engine.get_sample_rate()
                duration = self.parent().parent().engine.get_duration()
                total_samples = sample_rate * duration
                max_zoom = total_samples / 100  # At least 100 samples visible
            except:
                pass

        # Zoom based on wheel direction
        delta = event.angleDelta().y()
        if delta > 0:
            # Zoom in
            old_zoom = self.zoom_level
            self.zoom_level = min(max_zoom, self.zoom_level * 1.2)

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

        # Calculate maximum zoom based on keeping at least 100 samples visible
        if hasattr(self.parent().parent(), 'engine'):
            try:
                sample_rate = self.parent().parent().engine.get_sample_rate()
                duration = self.parent().parent().engine.get_duration()
                total_samples = sample_rate * duration
                max_zoom = total_samples / 100  # At least 100 samples visible
                self.zoom_level = min(max_zoom, self.zoom_level * 1.5)
            except:
                self.zoom_level = min(10000.0, self.zoom_level * 1.5)
        else:
            self.zoom_level = min(10000.0, self.zoom_level * 1.5)

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