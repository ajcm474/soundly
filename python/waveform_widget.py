from PyQt6.QtWidgets import QWidget, QScrollBar
from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPen, QFont
import time


class WaveformWidget(QWidget):
    """Widget for displaying and interacting with audio waveforms from multiple tracks."""

    # signal emitted when track offset changes during drag
    track_offset_changed = pyqtSignal(int, float)

    def __init__(self):
        """Initialize waveform display with default view settings."""
        super().__init__()
        self.waveform_data = []
        self.track_info = []
        self.duration = 0.0
        self.max_timeline_duration = 0.0  # maximum extent including all track offsets
        self.selection_start = None
        self.selection_end = None
        self.selection_tracks = set()
        self.is_selecting = False
        self.playback_position = 0.0
        self.zoom_level = 1.0
        self.view_start_time = 0.0
        self.view_end_time = 0.0
        self.channels = 2
        self.auto_scroll = True

        # track dragging state
        self.is_dragging_track = False
        self.dragging_track_index = None
        self.drag_start_x = 0
        self.drag_start_offset = 0.0
        self.last_drag_update_time = 0.0  # for throttling drag updates

        # track header state
        self.track_header_height = 25  # height of draggable header bar

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

        if self.zoom_level > 100:
            parts.append(f"{seconds:.3f}s")
        elif self.zoom_level > 10:
            parts.append(f"{seconds:.2f}s")
        elif self.zoom_level > 1:
            parts.append(f"{seconds:.1f}s")
        else:
            parts.append(f"{int(seconds)}s")

        return ''.join(parts) if parts else "0s"

    def set_waveform(self, data, duration, channels=None, track_info=None):
        """
        Update waveform data and display properties.

        Parameters
        ----------
        data : list of list of tuple
            waveform data per track as (min_l, max_l, min_r, max_r) tuples
        duration : float
            total audio duration in seconds
        channels : int, optional
            number of audio channels (1=mono, 2=stereo)
        track_info : list of tuple, optional
            track information as (name, sample_rate, channels, duration, start_offset) tuples

        Notes
        -----
        Resets view to show full waveform if at default zoom level.
        """
        self.waveform_data = data
        self.duration = duration
        self.channels = channels if channels else 2
        self.track_info = track_info if track_info else []

        self.is_stereo = self.channels == 2

        # calculate maximum timeline duration including track offsets
        old_max_duration = self.max_timeline_duration
        if self.track_info:
            self.max_timeline_duration = max(
                (info[4] + info[3] if len(info) > 4 else info[3])
                for info in self.track_info
            )
        else:
            self.max_timeline_duration = duration

        # handle view bounds when timeline duration changes
        if old_max_duration == 0:
            # first load - show full timeline
            self.view_start_time = 0.0
            self.view_end_time = self.max_timeline_duration
        elif old_max_duration > 0 and self.max_timeline_duration > old_max_duration:
            # timeline extended (e.g., from dragging)
            # keep the same visible duration, don't zoom out
            current_visible_duration = self.view_end_time - self.view_start_time
            # if we're viewing the end, follow it
            if self.view_end_time >= old_max_duration - 0.01:
                self.view_end_time = self.max_timeline_duration
                self.view_start_time = max(0.0, self.view_end_time - current_visible_duration)
            # otherwise keep current view (no zoom change)
        elif old_max_duration > 0 and self.max_timeline_duration < old_max_duration:
            # timeline shrunk - adjust view if needed
            if self.view_end_time > self.max_timeline_duration:
                self.view_end_time = self.max_timeline_duration
                self.view_start_time = max(0.0, self.view_start_time)

        self.update()

    def _update_parent_waveform(self):
        parent = self.parent()
        if parent and hasattr(parent.parent(), 'update_waveform'):
            parent.parent().update_waveform()

    def get_track_at_y(self, y):
        """
        Determine which track is at the given y coordinate.

        Parameters
        ----------
        y : float
            y coordinate in pixels

        Returns
        -------
        int or None
            track index, or None if outside track area
        """
        ruler_height = 30
        if y < ruler_height:
            return None

        num_tracks = len(self.waveform_data)
        if num_tracks == 0:
            return None

        waveform_height = self.height() - ruler_height
        track_height = waveform_height / num_tracks

        track_idx = int((y - ruler_height) / track_height)
        if track_idx < 0 or track_idx >= num_tracks:
            return None

        return track_idx

    def is_on_track_header(self, x, y, track_idx):
        """
        Check if coordinates are within the track header (draggable bar).

        Parameters
        ----------
        x : float
            x coordinate in pixels
        y : float
            y coordinate in pixels
        track_idx : int
            track index to check

        Returns
        -------
        bool
            True if within the track's header bar
        """
        if track_idx is None or track_idx >= len(self.track_info):
            return False

        ruler_height = 30
        waveform_height = self.height() - ruler_height
        num_tracks = len(self.waveform_data)
        track_height = waveform_height / num_tracks

        track_y_start = ruler_height + (track_idx * track_height)
        track_header_end = track_y_start + self.track_header_height

        return track_y_start <= y <= track_header_end

    def is_on_audio_block(self, x, track_idx):
        """
        Check if x coordinate is within the audio block of a track.

        Parameters
        ----------
        x : float
            x coordinate in pixels
        track_idx : int
            track index to check

        Returns
        -------
        bool
            True if x is within the track's audio block
        """
        if track_idx is None or track_idx >= len(self.track_info):
            return False

        info = self.track_info[track_idx]
        track_duration = info[3]
        track_offset = info[4] if len(info) > 4 else 0.0

        track_start_time = track_offset
        track_end_time = track_offset + track_duration

        click_time = self.x_to_time(x)
        return track_start_time <= click_time <= track_end_time

    def update_view_bounds(self):
        """Ensure view bounds are valid and within maximum timeline duration."""
        if self.max_timeline_duration == 0:
            return

        visible_duration = self.max_timeline_duration / self.zoom_level

        # ensure we don't go past the end
        if self.view_start_time + visible_duration > self.max_timeline_duration:
            self.view_start_time = max(0.0, self.max_timeline_duration - visible_duration)

        self.view_end_time = min(self.view_start_time + visible_duration, self.max_timeline_duration)

    def paintEvent(self, event):
        """
        Render the waveform, selection, and playback cursor.

        Parameters
        ----------
        event : QPaintEvent
            paint event details

        Notes
        -----
        Draws time ruler, track waveforms with separators, selection highlight
        per track, and playback position indicator. Shorter tracks show black
        space after their duration.
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

        if not self.waveform_data or self.max_timeline_duration == 0:
            return

        self.draw_time_ruler(painter, width, ruler_height)

        painter.save()
        painter.translate(0, ruler_height)

        visible_duration = self.view_end_time - self.view_start_time
        if visible_duration <= 0:
            painter.restore()
            return

        num_tracks = len(self.waveform_data)
        if num_tracks == 0:
            painter.restore()
            return

        track_height = waveform_height / num_tracks

        # alternate colors to differentiate tracks visually
        track_colors = [
            QColor(100, 200, 255),      # light blue
            QColor(255, 150, 100),      # orange
            QColor(150, 255, 100),      # lime green
            QColor(255, 100, 255),      # pink
            QColor(255, 255, 100),      # yellow
        ]

        # draw each track
        for track_idx, track_data in enumerate(self.waveform_data):
            track_y_offset = track_idx * track_height
            track_color = track_colors[track_idx % len(track_colors)]

            # draw grey barrier between tracks
            if track_idx > 0:
                painter.setPen(QPen(QColor(100, 100, 100), 2))
                painter.drawLine(0, int(track_y_offset), width, int(track_y_offset))

            # get track info
            info = self.track_info[track_idx] if track_idx < len(self.track_info) else None
            track_offset = info[4] if info and len(info) > 4 else 0.0
            track_duration = info[3] if info else 0.0

            # calculate pixel positions for this track's audio block
            track_start_time = track_offset
            track_end_time = track_offset + track_duration

            # only draw if track overlaps with visible range
            if track_end_time > self.view_start_time and track_start_time < self.view_end_time:
                # convert track times to pixel positions
                start_x = self.time_to_x(track_start_time)
                end_x = self.time_to_x(track_end_time)

                # clip to visible area
                start_x = max(0, start_x)
                end_x = min(width, end_x)

                block_width = end_x - start_x

                # draw track header bar (only over audio block, like Audacity)
                if block_width > 0:
                    header_bg = QColor(60, 60, 60)
                    painter.fillRect(
                        int(start_x),
                        int(track_y_offset),
                        int(block_width),
                        self.track_header_height,
                        header_bg
                    )

                    # draw subtle top border
                    painter.setPen(QPen(QColor(80, 80, 80), 1))
                    painter.drawLine(int(start_x), int(track_y_offset), int(end_x), int(track_y_offset))

                    # draw track name in header
                    if info:
                        painter.setPen(QPen(QColor(220, 220, 220), 1))
                        font = painter.font()
                        font.setPointSize(9)
                        font.setBold(False)
                        painter.setFont(font)
                        text_rect = QRectF(start_x + 5, track_y_offset + 2, block_width - 10, self.track_header_height - 4)
                        painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, info[0])

                    # draw audio block background (slightly lighter than track header)
                    painter.fillRect(
                        int(start_x),
                        int(track_y_offset + self.track_header_height),
                        int(block_width),
                        int(track_height - self.track_header_height),
                        QColor(40, 40, 40)
                    )

                    # calculate which part of waveform data to draw
                    # waveform_data corresponds to the visible time range (view_start_time to view_end_time)
                    # we need to map from the audio block's time range to the waveform data indices

                    # calculate what portion of the visible range the audio block occupies
                    visible_start = max(track_start_time, self.view_start_time)
                    visible_end = min(track_end_time, self.view_end_time)

                    # convert to fractions of the visible time range
                    start_fraction = (visible_start - self.view_start_time) / visible_duration
                    end_fraction = (visible_end - self.view_start_time) / visible_duration

                    # map to waveform data indices
                    data_start_idx = int(start_fraction * len(track_data))
                    data_end_idx = int(end_fraction * len(track_data))
                    data_start_idx = max(0, min(data_start_idx, len(track_data) - 1))
                    data_end_idx = max(data_start_idx + 1, min(data_end_idx, len(track_data)))

                    # draw waveform
                    painter.setPen(QPen(track_color, 1))

                    if self.is_stereo:
                        # stereo: draw left and right channels
                        left_center = track_y_offset + self.track_header_height + (track_height - self.track_header_height) * 0.25
                        right_center = track_y_offset + self.track_header_height + (track_height - self.track_header_height) * 0.75
                        channel_height = (track_height - self.track_header_height) * 0.25

                        for i in range(data_start_idx, data_end_idx):
                            if i >= len(track_data):
                                break

                            min_l, max_l, min_r, max_r = track_data[i]

                            # calculate x position for this data point
                            # waveform_data[i] represents a specific time in the view range
                            # map index to time in full view range
                            time_fraction = i / max(1, len(track_data) - 1)
                            time_at_point = self.view_start_time + time_fraction * (self.view_end_time - self.view_start_time)
                            x = self.time_to_x(time_at_point)

                            # when zoomed in enough that samples are visible individually
                            if abs(max_l - min_l) < 0.001:
                                # draw single sample as line from center to value
                                y_top = left_center - (max_l * channel_height)
                                painter.drawLine(
                                    QPointF(x, left_center),
                                    QPointF(x, y_top)
                                )
                            else:
                                # draw waveform envelope
                                y_max = left_center - (max_l * channel_height)
                                y_min = left_center - (min_l * channel_height)
                                painter.drawLine(QPointF(x, y_min), QPointF(x, y_max))

                            # right channel
                            if abs(max_r - min_r) < 0.001:
                                y_top = right_center - (max_r * channel_height)
                                painter.drawLine(
                                    QPointF(x, right_center),
                                    QPointF(x, y_top)
                                )
                            else:
                                y_max = right_center - (max_r * channel_height)
                                y_min = right_center - (min_r * channel_height)
                                painter.drawLine(QPointF(x, y_min), QPointF(x, y_max))
                    else:
                        # mono: draw single waveform
                        center_y = track_y_offset + self.track_header_height + (track_height - self.track_header_height) / 2
                        channel_height = (track_height - self.track_header_height) / 2

                        for i in range(data_start_idx, data_end_idx):
                            if i >= len(track_data):
                                break

                            min_l, max_l, _, _ = track_data[i]

                            # calculate x position for this data point
                            # waveform_data[i] represents a specific time in the view range
                            # map index to time in full view range
                            time_fraction = i / max(1, len(track_data) - 1)
                            time_at_point = self.view_start_time + time_fraction * (self.view_end_time - self.view_start_time)
                            x = self.time_to_x(time_at_point)

                            if abs(max_l - min_l) < 0.001:
                                y_top = center_y - (max_l * channel_height)
                                painter.drawLine(
                                    QPointF(x, center_y),
                                    QPointF(x, y_top)
                                )
                            else:
                                y_max = center_y - (max_l * channel_height)
                                y_min = center_y - (min_l * channel_height)
                                painter.drawLine(QPointF(x, y_min), QPointF(x, y_max))

            # draw selection highlight for this track
            if track_idx in self.selection_tracks and self.selection_start is not None and self.selection_end is not None:
                sel_start = min(self.selection_start, self.selection_end)
                sel_end = max(self.selection_start, self.selection_end)

                sel_start_x = self.time_to_x(sel_start)
                sel_end_x = self.time_to_x(sel_end)

                painter.fillRect(
                    int(sel_start_x),
                    int(track_y_offset),
                    int(sel_end_x - sel_start_x),
                    int(track_height),
                    QColor(255, 255, 255, 50)
                )

        # draw playback position indicator
        if self.playback_position > 0:
            playback_x = self.time_to_x(self.playback_position)
            if 0 <= playback_x <= width:
                painter.setPen(QPen(QColor(255, 0, 0), 2))
                painter.drawLine(int(playback_x), 0, int(playback_x), int(waveform_height))

        painter.restore()

    def draw_time_ruler(self, painter, width, ruler_height):
        """
        Draw time ruler at top of waveform display.

        Parameters
        ----------
        painter : QPainter
            painter object for drawing
        width : int
            width of widget in pixels
        ruler_height : int
            height of ruler in pixels

        Notes
        -----
        Automatically adjusts time mark spacing based on zoom level.
        """
        painter.fillRect(0, 0, width, ruler_height, QColor(50, 50, 50))

        if self.max_timeline_duration == 0:
            return

        visible_duration = self.view_end_time - self.view_start_time
        if visible_duration <= 0:
            return

        # determine appropriate time interval for marks
        intervals = [
            0.001,
            0.005,
            0.01,
            0.025,
            0.05,
            0.1,
            1.0,
            5.0,
            10.0,
            30.0,
            60.0,
            300.0,
            600.0,
        ]

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

            label = self.format_time(current_time)

            rect = QRectF(x - 40, 2, 80, ruler_height - 12)
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, label)

            current_time += interval

    def mousePressEvent(self, event):
        """
        Handle mouse press to start selection or track dragging.

        Parameters
        ----------
        event : QMouseEvent
            mouse event details

        Notes
        -----
        Clicking on track header starts dragging; regular click starts selection.
        """
        if event.button() == Qt.MouseButton.LeftButton:
            if event.position().y() < 30:
                return

            track_idx = self.get_track_at_y(event.position().y())
            if track_idx is None:
                return

            # check if clicking on track header (draggable area)
            if self.is_on_track_header(event.position().x(), event.position().y(), track_idx):
                if self.is_on_audio_block(event.position().x(), track_idx):
                    # start dragging this track
                    self.is_dragging_track = True
                    self.dragging_track_index = track_idx
                    self.drag_start_x = event.position().x()
                    if track_idx < len(self.track_info) and len(self.track_info[track_idx]) > 4:
                        self.drag_start_offset = self.track_info[track_idx][4]
                    else:
                        self.drag_start_offset = 0.0
                    self.last_drag_update_time = time.time()
                    self.setCursor(Qt.CursorShape.ClosedHandCursor)
                    return

            # start selection
            self.is_selecting = True
            time_val = self.x_to_time(event.position().x())
            self.selection_start = time_val
            self.selection_end = time_val
            self.selection_tracks = {track_idx}
            self.update()

    def mouseMoveEvent(self, event):
        """
        Handle mouse drag to update selection or move track.

        Parameters
        ----------
        event : QMouseEvent
            mouse event details

        Notes
        -----
        Track dragging is throttled to ~30fps for performance.
        Updates cursor based on what's under the mouse.
        """
        if self.is_dragging_track and self.dragging_track_index is not None:
            # throttle updates to approximately 30fps for performance
            current_time = time.time()
            if current_time - self.last_drag_update_time < 0.033:  # ~30fps
                return

            self.last_drag_update_time = current_time

            # calculate new offset based on drag distance
            delta_x = event.position().x() - self.drag_start_x
            visible_duration = self.view_end_time - self.view_start_time
            delta_time = (delta_x / self.width()) * visible_duration

            new_offset = max(0.0, self.drag_start_offset + delta_time)

            # emit signal for parent to handle (which will update Rust and redraw)
            self.track_offset_changed.emit(self.dragging_track_index, new_offset)

        elif self.is_selecting:
            time_val = self.x_to_time(event.position().x())
            self.selection_end = time_val

            track_idx = self.get_track_at_y(event.position().y())
            if track_idx is not None:
                self.selection_tracks.add(track_idx)

            self.update()
        else:
            # update cursor based on what's under the mouse
            track_idx = self.get_track_at_y(event.position().y())
            if track_idx is not None:
                if self.is_on_track_header(event.position().x(), event.position().y(), track_idx):
                    if self.is_on_audio_block(event.position().x(), track_idx):
                        self.setCursor(Qt.CursorShape.OpenHandCursor)
                    else:
                        self.setCursor(Qt.CursorShape.ArrowCursor)
                else:
                    self.setCursor(Qt.CursorShape.ArrowCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)

    def mouseReleaseEvent(self, event):
        """
        Handle mouse release to finish selection or track dragging.

        Parameters
        ----------
        event : QMouseEvent
            mouse event details
        """
        if event.button() == Qt.MouseButton.LeftButton:
            if self.is_dragging_track:
                self.is_dragging_track = False
                self.dragging_track_index = None
                self.setCursor(Qt.CursorShape.ArrowCursor)
            else:
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
            sample_rate = self.parent().parent().engine.get_sample_rate()
            duration = self.parent().parent().engine.get_duration()
            total_samples = sample_rate * duration
            max_zoom = total_samples / 100

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
        if self.max_timeline_duration <= 0:
            return

        visible_duration = self.max_timeline_duration / new_zoom

        self.view_start_time = max(0.0, center_time - visible_duration / 2)
        self.view_end_time = min(self.max_timeline_duration, self.view_start_time + visible_duration)

        # adjust if we hit the end
        if self.view_end_time >= self.max_timeline_duration:
            self.view_end_time = self.max_timeline_duration
            self.view_start_time = max(0.0, self.max_timeline_duration - visible_duration)

        self._update_parent_waveform()

    def _center_on_mouse_position(self, event):
        """
        Center the zoom on the mouse position

        Parameters
        ----------
        event : QWheelEvent
            wheel event details
        """
        mouse_time = self.x_to_time(event.position().x())
        mouse_frac = event.position().x() / self.width()
        visible_duration = self.max_timeline_duration / self.zoom_level

        self.view_start_time = max(0, mouse_time - (mouse_frac * visible_duration))
        self.view_end_time = min(self.max_timeline_duration, self.view_start_time + visible_duration)

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
        max_zoom = self._get_max_zoom()
        old_zoom = self.zoom_level

        delta = event.angleDelta().y()

        if delta > 0:
            # zoom in
            self.zoom_level = min(max_zoom, self.zoom_level * 1.2)

            if self.zoom_level != old_zoom and self.max_timeline_duration > 0:
                self._center_on_mouse_position(event)
                self._update_parent_waveform()

        elif delta < 0:
            # zoom out
            self.zoom_level = max(1.0, self.zoom_level / 1.2)

            if self.zoom_level != old_zoom and self.max_timeline_duration > 0:
                if self.zoom_level == 1.0:
                    self.view_start_time = 0.0
                    self.view_end_time = self.max_timeline_duration
                else:
                    self._center_on_mouse_position(event)

                self._update_parent_waveform()

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
        Get current selection time range and affected tracks.

        Returns
        -------
        tuple or None
            ((start_time, end_time), set of track indices), or None if no valid selection

        Notes
        -----
        Minimum selection size is 1ms to prevent accidental point selections.
        """
        if (
            self.selection_start is not None and
            self.selection_end is not None and
            abs(self.selection_end - self.selection_start) > 0.001
        ):
            return ((min(self.selection_start, self.selection_end),
                     max(self.selection_start, self.selection_end)),
                    self.selection_tracks.copy())
        return None

    def clear_selection(self):
        """Clear the current selection and update display."""
        self.selection_start = None
        self.selection_end = None
        self.selection_tracks = set()
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

        if self.auto_scroll and self.zoom_level > 1.0:
            visible_duration = self.max_timeline_duration / self.zoom_level
            needs_parent_update = False

            # scroll right when approaching right edge
            if position > self.view_start_time + visible_duration * 0.9:
                new_start = position - visible_duration * 0.1
                self.view_start_time = max(0.0, min(new_start, self.max_timeline_duration - visible_duration))
                needs_parent_update = True

            # scroll left when playback should start before current view
            elif position < self.view_start_time:
                self.view_start_time = max(0.0, position)
                needs_parent_update = True

            if needs_parent_update:
                self.view_end_time = self.view_start_time + visible_duration
                self._update_parent_waveform()

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

        if self.zoom_level != old_zoom and self.max_timeline_duration > 0:
            selection = self.get_selection()
            if selection:
                sel_start, sel_end = selection[0]
                center_time = (sel_start + sel_end) / 2
            else:
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

        if self.zoom_level != old_zoom and self.max_timeline_duration > 0:
            if self.zoom_level == 1.0:
                # show entire waveform
                self.view_start_time = 0.0
                self.view_end_time = self.max_timeline_duration
                self._update_parent_waveform()
            else:
                # try to keep the current center
                center_time = (self.view_start_time + self.view_end_time) / 2
                self._update_view_for_zoom(center_time, self.zoom_level)