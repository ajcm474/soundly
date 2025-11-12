from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import QPainter, QColor, QPen


class WaveformWidget(QWidget):
    """Widget for displaying and interacting with audio waveforms."""

    def __init__(self):
        """Initialize waveform display with default view settings."""
        super().__init__()
        self.waveform_data = []
        self.duration = 0.0
        self.selection_start = None
        self.selection_end = None
        self.is_selecting = False
        self.playback_position = 0.0
        self.zoom_level = 1.0
        self.view_start_time = 0.0
        self.view_end_time = 0.0
        self.is_stereo = False
        self.channels = 2
        self.auto_scroll = True

        self.setMinimumHeight(200)
        self.setMouseTracking(True)

    def format_time(self, time_seconds):
        """
        Format time value for display based on current zoom level.

        Parameters
        ----------
        time_seconds : float
            time in seconds

        Returns
        -------
        str
            formatted time string with appropriate precision

        Notes
        -----
        Precision increases with zoom level to show milliseconds when
        viewing individual samples.
        """
        hours = int(time_seconds // 3600)
        minutes = int((time_seconds % 3600) // 60)
        seconds = time_seconds % 60

        parts = []
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")

        # format seconds based on zoom level
        if self.zoom_level > 100:
            parts.append(f"{seconds:.3f}s")
        elif self.zoom_level > 10:
            parts.append(f"{seconds:.2f}s")
        elif self.zoom_level > 1:
            parts.append(f"{seconds:.1f}s")
        else:
            parts.append(f"{int(seconds)}s")

        return ''.join(parts) if parts else "0s"

    def set_waveform(self, data, duration, channels=None):
        """
        Update waveform data and display properties.

        Parameters
        ----------
        data : list of tuple
            waveform data as (min_l, max_l, min_r, max_r) tuples
        duration : float
            total audio duration in seconds
        channels : int, optional
            number of audio channels (1=mono, 2=stereo)

        Notes
        -----
        Resets view to show full waveform if at default zoom level.
        """
        self.waveform_data = data
        self.duration = duration
        self.channels = channels if channels else 2

        self.is_stereo = self.channels == 2

        # initialize view to show full waveform if at default zoom
        if self.zoom_level == 1.0:
            self.view_start_time = 0.0
            self.view_end_time = duration
        else:
            # keep current zoom level but ensure we're within bounds
            self.update_view_bounds()

        self.update()

    def update_view_bounds(self):
        """Ensure view bounds are valid and within audio duration."""
        if self.duration == 0:
            return

        visible_duration = self.duration / self.zoom_level

        # ensure we don't go past the end
        if self.view_start_time + visible_duration > self.duration:
            self.view_start_time = max(0, self.duration - visible_duration)

        self.view_end_time = min(self.view_start_time + visible_duration, self.duration)

    def paintEvent(self, event):
        """
        Render the waveform, selection, and playback cursor.

        Parameters
        ----------
        event : QPaintEvent
            paint event details

        Notes
        -----
        Draws time ruler, stereo/mono waveform with appropriate scaling,
        selection highlight, and playback position indicator.
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        width = self.width()
        height = self.height()

        # reserve space for time ruler
        ruler_height = 30
        waveform_height = height - ruler_height

        # background
        painter.fillRect(self.rect(), QColor(30, 30, 30))

        if not self.waveform_data or self.duration == 0:
            return

        self.draw_time_ruler(painter, width, ruler_height)

        painter.save()
        painter.translate(0, ruler_height)

        visible_duration = self.view_end_time - self.view_start_time
        if visible_duration <= 0:
            painter.restore()
            return

        # draw selection highlight
        if self.selection_start is not None and self.selection_end is not None:
            sel_start = min(self.selection_start, self.selection_end)
            sel_end = max(self.selection_start, self.selection_end)

            # only draw if selection is visible
            if sel_end >= self.view_start_time and sel_start <= self.view_end_time:
                start_x = self.time_to_x(sel_start)
                end_x = self.time_to_x(sel_end)
                painter.fillRect(QRectF(start_x, 0, end_x - start_x, waveform_height),
                                 QColor(100, 150, 255, 80))

        total_samples = len(self.waveform_data)
        if total_samples == 0:
            painter.restore()
            return

        if self.is_stereo and self.channels == 2:
            # stereo waveform
            channel_height = waveform_height / 2

            # center lines for each channel
            painter.setPen(QPen(QColor(80, 80, 80), 1))
            painter.drawLine(0, int(channel_height / 2), width, int(channel_height / 2))
            painter.drawLine(0, int(channel_height + channel_height / 2),
                             width, int(channel_height + channel_height / 2))

            # channel labels
            painter.setPen(QPen(QColor(150, 150, 150), 1))
            painter.drawText(5, 15, "L")
            painter.drawText(5, int(channel_height + 15), "R")

            # draw waveforms
            painter.setPen(QPen(QColor(100, 200, 255), 1))

            for i in range(total_samples):
                if i >= len(self.waveform_data):
                    break

                # when zoomed in to individual samples, we have more data points than pixels
                # map sample position to x coordinate based on the number of samples
                if total_samples > width:
                    # individual sample mode: map samples across the width
                    x = (i / total_samples) * width
                else:
                    # normal mode: one data point per pixel
                    x = (i / total_samples) * width

                # get stereo data
                min_l, max_l, min_r, max_r = self.waveform_data[i]

                # left channel
                y_min_l = (channel_height / 2) - (min_l * channel_height * 0.45)
                y_max_l = (channel_height / 2) - (max_l * channel_height * 0.45)
                painter.drawLine(QPointF(x, y_min_l), QPointF(x, y_max_l))

                # right channel
                y_min_r = channel_height + (channel_height / 2) - (min_r * channel_height * 0.45)
                y_max_r = channel_height + (channel_height / 2) - (max_r * channel_height * 0.45)
                painter.drawLine(QPointF(x, y_min_r), QPointF(x, y_max_r))
        else:
            # mono waveform
            center_y = waveform_height / 2

            # draw center line
            painter.setPen(QPen(QColor(80, 80, 80), 1))
            painter.drawLine(0, int(center_y), width, int(center_y))

            # draw waveform
            painter.setPen(QPen(QColor(100, 200, 255), 1))

            for i in range(total_samples):
                if i >= len(self.waveform_data):
                    break

                # map sample position to x coordinate
                if total_samples > width:
                    # individual sample mode: map samples across the width
                    x = (i / total_samples) * width
                else:
                    # normal mode: one data point per pixel
                    x = (i / total_samples) * width

                # get mono data (from first two values)
                min_val, max_val = self.waveform_data[i][:2]

                y_min = center_y - (min_val * center_y * 0.9)
                y_max = center_y - (max_val * center_y * 0.9)

                painter.drawLine(QPointF(x, y_min), QPointF(x, y_max))

        painter.restore()

        # draw playback cursor
        if (self.playback_position > 0 and
                self.playback_position >= self.view_start_time and
                self.playback_position <= self.view_end_time):
            x = self.time_to_x(self.playback_position)
            painter.setPen(QPen(QColor(255, 100, 100), 2))
            painter.drawLine(int(x), 0, int(x), height)

    def draw_time_ruler(self, painter, width, ruler_height):
        """
        Draw time ruler with adaptive intervals.

        Parameters
        ----------
        painter : QPainter
            painter object for drawing
        width : int
            widget width in pixels
        ruler_height : int
            height of ruler area in pixels

        Notes
        -----
        Automatically adjusts time intervals based on zoom level to
        maintain readable spacing between marks.
        """
        painter.fillRect(0, 0, width, ruler_height, QColor(40, 40, 40))

        # border line
        painter.setPen(QPen(QColor(80, 80, 80), 1))
        painter.drawLine(0, ruler_height - 1, width, ruler_height - 1)

        visible_duration = self.view_end_time - self.view_start_time

        # choose appropriate time interval
        intervals = [
            0.001,
            0.01,
            0.1,
            1.0,
            5.0,
            10.0,
            30.0,
            60.0,
            300.0,
            600.0,
        ]

        # find appropriate interval (aim for 50-200 pixels between marks)
        target_spacing = 100
        time_per_pixel = visible_duration / width
        ideal_interval = target_spacing * time_per_pixel

        interval = intervals[0]

        for int_val in intervals:
            if int_val >= ideal_interval * 0.5:
                interval = int_val
                break

        # draw time marks
        painter.setPen(QPen(QColor(200, 200, 200), 1))
        font = painter.font()
        font.setPointSize(8)
        painter.setFont(font)

        # start from the first interval mark after view_start_time
        first_mark = (self.view_start_time // interval) * interval
        if first_mark < self.view_start_time:
            first_mark += interval

        current_time = first_mark
        while current_time <= self.view_end_time:
            x = self.time_to_x(current_time)

            # draw tick mark
            painter.drawLine(int(x), ruler_height - 10, int(x), ruler_height - 1)

            # format time label using the new formatter
            label = self.format_time(current_time)

            # draw label
            rect = QRectF(x - 40, 2, 80, ruler_height - 12)
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, label)

            current_time += interval

    def mousePressEvent(self, event):
        """
        Handle mouse press to start selection.

        Parameters
        ----------
        event : QMouseEvent
            mouse event details

        Notes
        -----
        Ignores clicks in the ruler area at top of widget.
        """
        if event.button() == Qt.MouseButton.LeftButton:
            # ignore clicks in the ruler area
            if event.position().y() < 30:
                return

            self.is_selecting = True
            time = self.x_to_time(event.position().x())
            self.selection_start = time
            self.selection_end = time
            self.update()

    def mouseMoveEvent(self, event):
        """
        Handle mouse drag to update selection.

        Parameters
        ----------
        event : QMouseEvent
            mouse event details
        """
        if self.is_selecting:
            time = self.x_to_time(event.position().x())
            self.selection_end = time
            self.update()

    def mouseReleaseEvent(self, event):
        """
        Handle mouse release to finish selection.

        Parameters
        ----------
        event : QMouseEvent
            mouse event details
        """
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_selecting = False

    def _get_max_zoom(self):
        """
        Calculate maximum zoom level based on sample rate.

        Returns
        -------
        float
            maximum zoom level to keep at least 100 samples visible
        """
        max_zoom = 10000.0
        if hasattr(self.parent().parent(), 'engine'):
            try:
                sample_rate = self.parent().parent().engine.get_sample_rate()
                duration = self.parent().parent().engine.get_duration()
                total_samples = sample_rate * duration
                max_zoom = total_samples / 100
            except:
                pass
        return max_zoom

    def _update_view_for_zoom(self, center_time, new_zoom):
        """
        Update view bounds after zoom change, centering on specified time.

        Parameters
        ----------
        center_time : float
            time in seconds to center the view on
        new_zoom : float
            new zoom level

        Notes
        -----
        Requests waveform redraw from parent after updating bounds.
        """
        if self.duration <= 0:
            return

        visible_duration = self.duration / new_zoom

        self.view_start_time = center_time - visible_duration / 2
        self.view_start_time = max(0, self.view_start_time)
        self.view_end_time = min(self.duration, self.view_start_time + visible_duration)

        # adjust if we hit the end
        if self.view_end_time >= self.duration:
            self.view_end_time = self.duration
            self.view_start_time = max(0, self.duration - visible_duration)

        # request waveform redraw from parent
        parent = self.parent()
        if parent and hasattr(parent.parent(), 'update_waveform'):
            parent.parent().update_waveform()

    def wheelEvent(self, event):
        """
        Handle mouse wheel for zooming.

        Parameters
        ----------
        event : QWheelEvent
            wheel event details

        Notes
        -----
        Zooms centered on mouse position. automatically calculates
        maximum zoom based on sample rate to prevent zooming beyond
        individual samples.
        """
        mouse_time = self.x_to_time(event.position().x())
        max_zoom = self._get_max_zoom()

        delta = event.angleDelta().y()
        if delta > 0:
            # zoom in
            old_zoom = self.zoom_level
            self.zoom_level = min(max_zoom, self.zoom_level * 1.2)

            if self.zoom_level != old_zoom and self.duration > 0:
                visible_duration = self.duration / self.zoom_level

                # center on mouse position
                self.view_start_time = mouse_time - (event.position().x() / self.width()) * visible_duration
                self.view_start_time = max(0, self.view_start_time)
                self.view_end_time = min(self.duration, self.view_start_time + visible_duration)

                # request waveform redraw
                parent = self.parent()
                if parent and hasattr(parent.parent(), 'update_waveform'):
                    parent.parent().update_waveform()
        elif delta < 0:
            # zoom out
            old_zoom = self.zoom_level
            self.zoom_level = max(1.0, self.zoom_level / 1.2)

            if self.zoom_level != old_zoom and self.duration > 0:
                if self.zoom_level == 1.0:
                    self.view_start_time = 0.0
                    self.view_end_time = self.duration
                else:
                    visible_duration = self.duration / self.zoom_level

                    # try to keep mouse position stable
                    self.view_start_time = mouse_time - (event.position().x() / self.width()) * visible_duration
                    self.view_start_time = max(0, self.view_start_time)
                    self.view_end_time = min(self.duration, self.view_start_time + visible_duration)

                # request waveform redraw
                parent = self.parent()
                if parent and hasattr(parent.parent(), 'update_waveform'):
                    parent.parent().update_waveform()

        event.accept()

    def time_to_x(self, time):
        """
        Convert time value to x coordinate in current view.

        Parameters
        ----------
        time : float
            time in seconds

        Returns
        -------
        float
            x coordinate in pixels
        """
        if self.view_end_time == self.view_start_time:
            return 0
        fraction = (time - self.view_start_time) / (self.view_end_time - self.view_start_time)
        return fraction * self.width()

    def x_to_time(self, x):
        """
        Convert x coordinate to time value in current view.

        Parameters
        ----------
        x : float
            x coordinate in pixels

        Returns
        -------
        float
            time in seconds
        """
        if self.width() == 0:
            return self.view_start_time
        fraction = x / self.width()
        return self.view_start_time + fraction * (self.view_end_time - self.view_start_time)

    def get_selection(self):
        """
        Get current selection time range.

        Returns
        -------
        tuple of float or None
            (start_time, end_time) in seconds, or None if no valid selection

        Notes
        -----
        Minimum selection size is 1ms to prevent accidental point selections.
        """
        if self.selection_start is not None and self.selection_end is not None:
            if abs(self.selection_end - self.selection_start) > 0.001:
                return (min(self.selection_start, self.selection_end),
                        max(self.selection_start, self.selection_end))
        return None

    def clear_selection(self):
        """Clear the current selection and update display."""
        self.selection_start = None
        self.selection_end = None
        self.update()

    def set_playback_position(self, position):
        """
        Update playback cursor position with auto-scrolling.

        Parameters
        ----------
        position : float
            playback position in seconds

        Notes
        -----
        Automatically scrolls the view when zoomed in to keep the
        playback cursor visible near the right edge.
        """
        self.playback_position = position

        # auto-scroll to follow playback if zoomed in
        if self.auto_scroll and self.zoom_level > 1.0:
            visible_duration = self.duration / self.zoom_level

            # scroll when approaching right edge
            if position > self.view_start_time + visible_duration * 0.9:
                # scroll forward by half the visible duration
                new_start = position - visible_duration * 0.1
                self.view_start_time = max(0, min(new_start, self.duration - visible_duration))
                self.view_end_time = self.view_start_time + visible_duration

                # request new waveform data for the new view
                parent = self.parent()
                if parent and hasattr(parent.parent(), 'update_waveform'):
                    parent.parent().update_waveform()

            # scroll when before view
            elif position < self.view_start_time:
                self.view_start_time = max(0, position)
                self.view_end_time = self.view_start_time + visible_duration

                # request new waveform data for the new view
                parent = self.parent()
                if parent and hasattr(parent.parent(), 'update_waveform'):
                    parent.parent().update_waveform()

        self.update()

    def clear_playback_position(self):
        """Reset playback cursor to beginning and update display."""
        self.playback_position = 0.0
        self.update()

    def zoom_in(self):
        """
        Zoom in on waveform, centered on selection or current view.

        Notes
        -----
        Respects maximum zoom level based on sample rate. Centers on
        selection if one exists, otherwise centers on current view.
        """
        old_zoom = self.zoom_level
        max_zoom = self._get_max_zoom()
        self.zoom_level = min(max_zoom, self.zoom_level * 1.5)

        if self.zoom_level != old_zoom and self.duration > 0:
            selection = self.get_selection()
            if selection:
                # center on selection
                sel_start, sel_end = selection
                center_time = (sel_start + sel_end) / 2
            else:
                # center on current view
                center_time = (self.view_start_time + self.view_end_time) / 2

            self._update_view_for_zoom(center_time, self.zoom_level)

    def zoom_out(self):
        """
        Zoom out on waveform, maintaining current center.

        Notes
        -----
        Zooming out to minimum level (1.0) shows entire waveform.
        """
        old_zoom = self.zoom_level
        self.zoom_level = max(1.0, self.zoom_level / 1.5)

        if self.zoom_level != old_zoom and self.duration > 0:
            if self.zoom_level == 1.0:
                # show entire waveform
                self.view_start_time = 0.0
                self.view_end_time = self.duration
                # request waveform redraw from parent
                parent = self.parent()
                if parent and hasattr(parent.parent(), 'update_waveform'):
                    parent.parent().update_waveform()
            else:
                # try to keep the current center
                center_time = (self.view_start_time + self.view_end_time) / 2
                self._update_view_for_zoom(center_time, self.zoom_level)