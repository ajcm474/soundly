from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import QPainter, QColor, QPen, QFont


class WaveformWidget(QWidget):
    """Widget for displaying and interacting with audio waveforms from multiple tracks."""

    def __init__(self):
        """Initialize waveform display with default view settings."""
        super().__init__()
        self.waveform_data = []
        self.track_info = []
        self.duration = 0.0
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
            track information as (name, sample_rate, channels, duration) tuples

        Notes
        -----
        Resets view to show full waveform if at default zoom level.
        """
        self.waveform_data = data
        self.duration = duration
        self.channels = channels if channels else 2
        self.track_info = track_info if track_info else []

        self.is_stereo = self.channels == 2

        # initialize view to show full waveform if at default zoom
        if self.zoom_level == 1.0:
            self.view_start_time = 0.0
            self.view_end_time = duration
        else:
            # keep current zoom level but ensure we're within bounds
            self.update_view_bounds()

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
        """Ensure view bounds are valid and within audio duration."""
        if self.duration == 0:
            return

        visible_duration = self.duration / self.zoom_level

        # ensure we don't go past the end
        if self.view_start_time + visible_duration > self.duration:
            self.view_start_time = max(0.0, self.duration - visible_duration)

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

        if not self.waveform_data or self.duration == 0:
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

            if track_idx < len(self.track_info):
                info = self.track_info[track_idx]
                track_duration = info[3]
                track_channels = info[2]
                track_offset = info[4] if len(info) > 4 else 0.0
                label = f"{info[0]} ({info[1]}Hz, {'Stereo' if info[2] == 2 else 'Mono'})"
            else:
                track_duration = 0.0
                track_channels = 2
                track_offset = 0.0
                label = f"Track {track_idx + 1}"

            # calculate the audio block position on screen
            block_start_x = self.time_to_x(track_offset)
            block_end_x = self.time_to_x(track_offset + track_duration)

            # draw audio block background (slightly lighter than track background)
            if block_end_x > 0 and block_start_x < width:
                block_rect = QRectF(
                    max(0, block_start_x),
                    track_y_offset + 2,
                    min(width, block_end_x) - max(0, block_start_x),
                    track_height - 4
                )
                painter.fillRect(block_rect, QColor(45, 45, 45))

                # draw block border
                painter.setPen(QPen(QColor(80, 80, 80), 1))
                painter.drawRect(block_rect)

            # draw selection highlight ON TOP of block background
            if self.selection_start is not None and self.selection_end is not None:
                if track_idx in self.selection_tracks:
                    sel_start = min(self.selection_start, self.selection_end)
                    sel_end = max(self.selection_start, self.selection_end)

                    if sel_end >= self.view_start_time and sel_start <= self.view_end_time:
                        start_x = self.time_to_x(sel_start)
                        end_x = self.time_to_x(sel_end)
                        painter.fillRect(QRectF(start_x, track_y_offset, end_x - start_x, track_height),
                                         QColor(100, 150, 255, 80))

            # overlay track label in the block area
            painter.setPen(QPen(QColor(200, 200, 200), 1))
            font = painter.font()
            font.setPointSize(9)
            font.setBold(True)
            painter.setFont(font)
            label_x = max(5, block_start_x + 5)
            painter.drawText(int(label_x), int(track_y_offset + 15), label)

            total_samples = len(track_data)
            if total_samples == 0:
                continue

            is_stereo = track_channels == 2

            if is_stereo:
                channel_height = track_height / 2
                half_channel_height = channel_height / 2
                channel_height_plus_half = channel_height + half_channel_height
                channel_height_45percent = channel_height * 0.45

                painter.setPen(QPen(QColor(60, 60, 60), 1))
                painter.drawLine(0, int(track_y_offset + half_channel_height),
                                 width, int(track_y_offset + half_channel_height))
                painter.drawLine(0, int(track_y_offset + channel_height_plus_half),
                                 width, int(track_y_offset + channel_height_plus_half))

                painter.setPen(QPen(QColor(120, 120, 120), 1))
                painter.drawText(5, int(track_y_offset + half_channel_height + 5), "L")
                painter.drawText(5, int(track_y_offset + channel_height_plus_half + 5), "R")

                painter.setPen(QPen(track_color, 1))

                # Rust returns data at correct pixel positions (index = pixel x)
                # Just draw at each pixel position where there's non-zero data
                for i in range(total_samples):
                    if i >= len(track_data):
                        break

                    min_l, max_l, min_r, max_r = track_data[i]

                    # skip silent/zero samples
                    if min_l == 0.0 and max_l == 0.0 and min_r == 0.0 and max_r == 0.0:
                        continue

                    # x position is directly the index (pixel position)
                    x = i

                    y_min_l = track_y_offset + half_channel_height - (min_l * channel_height_45percent)
                    y_max_l = track_y_offset + half_channel_height - (max_l * channel_height_45percent)
                    painter.drawLine(QPointF(x, y_min_l), QPointF(x, y_max_l))

                    y_min_r = track_y_offset + channel_height_plus_half - (min_r * channel_height_45percent)
                    y_max_r = track_y_offset + channel_height_plus_half - (max_r * channel_height_45percent)
                    painter.drawLine(QPointF(x, y_min_r), QPointF(x, y_max_r))
            else:
                center_y = track_y_offset + track_height / 2
                track_height_45percent = track_height * 0.45

                painter.setPen(QPen(QColor(60, 60, 60), 1))
                painter.drawLine(0, int(center_y), width, int(center_y))

                painter.setPen(QPen(track_color, 1))

                # Rust returns data at correct pixel positions (index = pixel x)
                # Just draw at each pixel position where there's non-zero data
                for i in range(total_samples):
                    if i >= len(track_data):
                        break

                    min_val, max_val = track_data[i][:2]

                    # skip silent/zero samples
                    if min_val == 0.0 and max_val == 0.0:
                        continue

                    # x position is directly the index (pixel position)
                    x = i

                    y_min = center_y - (min_val * track_height_45percent)
                    y_max = center_y - (max_val * track_height_45percent)

                    painter.drawLine(QPointF(x, y_min), QPointF(x, y_max))

        painter.restore()

        # draw playback cursor if visible
        if (0 < self.playback_position <= self.view_end_time and
                self.playback_position >= self.view_start_time):
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
        Ignores clicks in the ruler area at top of widget. Alt+click on an
        audio block starts dragging; regular click starts selection.
        """
        if event.button() == Qt.MouseButton.LeftButton:
            if event.position().y() < 30:
                return

            track_idx = self.get_track_at_y(event.position().y())
            if track_idx is None:
                return

            # Alt+click to drag track, regular click for selection
            if event.modifiers() & Qt.KeyboardModifier.AltModifier:
                if self.is_on_audio_block(event.position().x(), track_idx):
                    # start dragging this track
                    self.is_dragging_track = True
                    self.dragging_track_index = track_idx
                    self.drag_start_x = event.position().x()
                    if track_idx < len(self.track_info) and len(self.track_info[track_idx]) > 4:
                        self.drag_start_offset = self.track_info[track_idx][4]
                    else:
                        self.drag_start_offset = 0.0
                    self.setCursor(Qt.CursorShape.ClosedHandCursor)
                    return

            # start selection
            self.is_selecting = True
            time = self.x_to_time(event.position().x())
            self.selection_start = time
            self.selection_end = time
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
        If dragging a track, updates its offset. Otherwise expands selection.
        Also updates cursor based on what's under the mouse.
        """
        if self.is_dragging_track and self.dragging_track_index is not None:
            # calculate new offset based on drag distance
            delta_x = event.position().x() - self.drag_start_x
            visible_duration = self.view_end_time - self.view_start_time
            delta_time = (delta_x / self.width()) * visible_duration

            new_offset = max(0.0, self.drag_start_offset + delta_time)

            # update the track offset via the engine
            parent = self.parent()
            if parent and hasattr(parent.parent(), 'engine'):
                try:
                    parent.parent().engine.set_track_offset(self.dragging_track_index, new_offset)
                    self._update_parent_waveform()
                except Exception as e:
                    print(f"Error setting track offset: {e}")

        elif self.is_selecting:
            time = self.x_to_time(event.position().x())
            self.selection_end = time

            track_idx = self.get_track_at_y(event.position().y())
            if track_idx is not None:
                self.selection_tracks.add(track_idx)

            self.update()
        else:
            # update cursor based on what's under the mouse (show hand when Alt is held)
            if event.modifiers() & Qt.KeyboardModifier.AltModifier:
                track_idx = self.get_track_at_y(event.position().y())
                if track_idx is not None and self.is_on_audio_block(event.position().x(), track_idx):
                    self.setCursor(Qt.CursorShape.OpenHandCursor)
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
        if self.duration <= 0:
            return

        visible_duration = self.duration / new_zoom

        self.view_start_time = max(0.0, center_time - visible_duration / 2)
        self.view_end_time = min(self.duration, self.view_start_time + visible_duration)

        # adjust if we hit the end
        if self.view_end_time >= self.duration:
            self.view_end_time = self.duration
            self.view_start_time = max(0.0, self.duration - visible_duration)

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
        visible_duration = self.duration / self.zoom_level

        self.view_start_time = max(0, mouse_time - (mouse_frac * visible_duration))
        self.view_end_time = min(self.duration, self.view_start_time + visible_duration)

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

            if self.zoom_level != old_zoom and self.duration > 0:
                self._center_on_mouse_position(event)
                self._update_parent_waveform()

        elif delta < 0:
            # zoom out
            self.zoom_level = max(1.0, self.zoom_level / 1.2)

            if self.zoom_level != old_zoom and self.duration > 0:
                if self.zoom_level == 1.0:
                    self.view_start_time = 0.0
                    self.view_end_time = self.duration
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
            visible_duration = self.duration / self.zoom_level
            needs_parent_update = False

            # scroll right when approaching right edge
            if position > self.view_start_time + visible_duration * 0.9:
                new_start = position - visible_duration * 0.1
                self.view_start_time = max(0.0, min(new_start, self.duration - visible_duration))
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

        if self.zoom_level != old_zoom and self.duration > 0:
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

        if self.zoom_level != old_zoom and self.duration > 0:
            if self.zoom_level == 1.0:
                # show entire waveform
                self.view_start_time = 0.0
                self.view_end_time = self.duration
                self._update_parent_waveform()
            else:
                # try to keep the current center
                center_time = (self.view_start_time + self.view_end_time) / 2
                self._update_view_for_zoom(center_time, self.zoom_level)