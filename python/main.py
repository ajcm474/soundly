import sys
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QPushButton, QFileDialog, QMessageBox,
                             QDialog, QComboBox, QLabel, QDialogButtonBox)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QKeySequence, QShortcut, QAction
from waveform_widget import WaveformWidget
import soundly


class ExportDialog(QDialog):
    """Dialog for configuring export options for different audio formats."""

    def __init__(self, parent=None, file_type="wav"):
        """
        Initialize the export dialog.

        Parameters
        ----------
        parent : QWidget, optional
            parent widget
        file_type : str
            type of file being exported ('wav', 'flac', or 'mp3')
        """
        super().__init__(parent)
        self.file_type = file_type
        self.setWindowTitle("Export Options")
        self.setModal(True)

        layout = QVBoxLayout()

        if file_type == "flac":
            layout.addWidget(QLabel("Compression Level:"))
            self.compression_combo = QComboBox()
            self.compression_combo.addItems([
                "0 - Fastest",
                "1", "2", "3", "4",
                "5 - Default",
                "6", "7", "8 - Best"
            ])
            self.compression_combo.setCurrentIndex(5)
            layout.addWidget(self.compression_combo)

        elif file_type == "mp3":
            layout.addWidget(QLabel("Bitrate:"))
            self.bitrate_combo = QComboBox()
            self.bitrate_combo.addItems([
                "128 kbps",
                "160 kbps",
                "192 kbps",     # default
                "256 kbps",
                "320 kbps"
            ])
            self.bitrate_combo.setCurrentIndex(2)
            layout.addWidget(self.bitrate_combo)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.setLayout(layout)

    def get_compression_level(self):
        """
        Get selected FLAC compression level.

        Returns
        -------
        int or None
            compression level 0-8, or None if not FLAC export
        """
        if self.file_type == "flac":
            return self.compression_combo.currentIndex()
        return None

    def get_bitrate(self):
        """
        Get selected MP3 bitrate.

        Returns
        -------
        int or None
            bitrate in kbps (128-320), or None if not MP3 export
        """
        if self.file_type == "mp3":
            text = self.bitrate_combo.currentText()
            return int(text.split()[0])
        return None


class ChannelExportDialog(QDialog):
    """Dialog for configuring channel export options."""

    def __init__(self, parent=None, has_stereo=False, num_mono=0):
        """
        Initialize the channel export dialog.

        Parameters
        ----------
        parent : QWidget, optional
            parent widget
        has_stereo : bool
            whether any stereo tracks are loaded
        num_mono : int
            number of mono tracks loaded
        """
        super().__init__(parent)
        self.setWindowTitle("Channel Options")
        self.setModal(True)

        layout = QVBoxLayout()

        layout.addWidget(QLabel("Output Channel Configuration:"))
        self.channel_combo = QComboBox()

        if has_stereo and num_mono == 0:
            self.channel_combo.addItems([
                "Stereo (keep as-is)",
                "Mono (mix down)",
                "Split to separate mono files"
            ])
        elif has_stereo and num_mono > 0:
            self.channel_combo.addItems([
                "Stereo (mix all)",
                "Mono (mix down all)",
            ])
        elif num_mono >= 2:
            self.channel_combo.addItems([
                "Mono (mix all)",
                "Stereo (first two tracks as L/R)",
            ])
        else:
            self.channel_combo.addItems([
                "Mono (keep as-is)",
            ])

        layout.addWidget(self.channel_combo)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.setLayout(layout)

    def get_channel_mode(self):
        """
        Get selected channel export mode.

        Returns
        -------
        str
            channel mode identifier ('stereo', 'mono', 'split', 'mono_to_stereo')
        """
        text = self.channel_combo.currentText().lower()
        if "split" in text:
            return "split"
        elif "stereo" in text and "first two" in text:
            return "mono_to_stereo"
        elif "stereo" in text:
            return "stereo"
        else:
            return "mono"


class AudioEditorWindow(QMainWindow):
    """Main application window for the audio editor."""

    def __init__(self):
        """Initialize the main window and audio engine."""
        super().__init__()
        self.engine = soundly.AudioEditor()
        self.is_repeating = False
        self.playback_timer = QTimer()
        self.playback_timer.timeout.connect(self.check_playback)
        self.playback_timer.start(50)

        self.init_ui()
        self.create_menu_bar()

    def create_menu_bar(self):
        """Create the application menu bar with file operations."""
        menubar = self.menuBar()

        file_menu = menubar.addMenu('File')

        # import submenu
        import_menu = file_menu.addMenu('Import')

        import_audio_action = QAction('Audio File...', self)
        import_audio_action.triggered.connect(self.import_file)
        import_menu.addAction(import_audio_action)

        clear_action = QAction('Clear All Tracks', self)
        clear_action.triggered.connect(self.clear_tracks)
        file_menu.addAction(clear_action)

        file_menu.addSeparator()

        # export submenu
        export_menu = file_menu.addMenu('Export')

        export_wav_action = QAction('WAV...', self)
        export_wav_action.triggered.connect(lambda: self.export_file('wav'))
        export_menu.addAction(export_wav_action)

        export_flac_action = QAction('FLAC...', self)
        export_flac_action.triggered.connect(lambda: self.export_file('flac'))
        export_menu.addAction(export_flac_action)

        export_mp3_action = QAction('MP3...', self)
        export_mp3_action.triggered.connect(lambda: self.export_file('mp3'))
        export_menu.addAction(export_mp3_action)

        file_menu.addSeparator()

        exit_action = QAction('Exit', self)
        exit_action.setShortcut('Ctrl+Q')
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

    def init_ui(self):
        """Initialize the user interface layout and controls."""
        self.setWindowTitle('Audio Editor')
        self.setGeometry(100, 100, 1200, 600)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)

        button_layout = QHBoxLayout()

        self.play_btn = QPushButton('Play')
        self.play_btn.clicked.connect(self.play)

        self.pause_btn = QPushButton('Pause')
        self.pause_btn.clicked.connect(self.pause)

        self.rewind_btn = QPushButton('⏮ Rewind')
        self.rewind_btn.clicked.connect(self.rewind)

        self.skip_btn = QPushButton('Skip ⏭')
        self.skip_btn.clicked.connect(self.skip_to_end)

        self.repeat_btn = QPushButton('🔁 Repeat: Off')
        self.repeat_btn.setCheckable(True)
        self.repeat_btn.clicked.connect(self.toggle_repeat)

        button_layout.addWidget(self.rewind_btn)
        button_layout.addWidget(self.play_btn)
        button_layout.addWidget(self.pause_btn)
        button_layout.addWidget(self.skip_btn)
        button_layout.addWidget(self.repeat_btn)
        button_layout.addStretch()

        self.waveform = WaveformWidget()

        main_layout.addLayout(button_layout)
        main_layout.addWidget(self.waveform)

        self.setup_shortcuts()

    def setup_shortcuts(self):
        """Configure keyboard shortcuts for common operations."""
        zoom_in = QShortcut(QKeySequence('Ctrl+='), self)
        zoom_in.activated.connect(self.waveform.zoom_in)

        # also support actual Ctrl+Plus for zoom in
        zoom_in_plus = QShortcut(QKeySequence.StandardKey.ZoomIn, self)
        zoom_in_plus.activated.connect(self.waveform.zoom_in)

        zoom_out = QShortcut(QKeySequence('Ctrl+-'), self)
        zoom_out.activated.connect(self.waveform.zoom_out)

        delete = QShortcut(QKeySequence(Qt.Key.Key_Delete), self)
        delete.activated.connect(self.delete_region)

        backspace = QShortcut(QKeySequence(Qt.Key.Key_Backspace), self)
        backspace.activated.connect(self.delete_region)

        space = QShortcut(QKeySequence(Qt.Key.Key_Space), self)
        space.activated.connect(self.toggle_playback)

    def import_file(self):
        """
        Open file dialog and import an audio file as a new track.

        Resets zoom and view to show the entire imported file.
        Displays error message if import fails. Shows warning if sample
        rates don't match existing tracks.
        """
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Audio File",
            "",
            "Audio Files (*.wav *.flac *.mp3);;All Files (*)"
        )

        if file_path:
            try:
                sample_rate, channels, mismatched_rate = self.engine.load_file(file_path)

                channel_str = "Stereo" if channels == 2 else "Mono"
                status_msg = f'Loaded: {file_path} ({sample_rate}Hz, {channel_str})'

                if mismatched_rate is not None:
                    QMessageBox.warning(
                        self,
                        'Sample Rate Mismatch',
                        f'Warning: This file has a sample rate of {sample_rate}Hz, '
                        f'but existing tracks use {mismatched_rate}Hz.\n\n'
                        f'Playback will use {mismatched_rate}Hz for all tracks, '
                        f'which may cause pitch/speed issues for this track.'
                    )
                    status_msg += f' [SAMPLE RATE MISMATCH: {mismatched_rate}Hz vs {sample_rate}Hz]'

                self.waveform.zoom_level = 1.0
                self.waveform.view_start_time = 0.0
                self.waveform.view_end_time = self.engine.get_duration()

                self.update_waveform()
                self.statusBar().showMessage(status_msg)
            except Exception as e:
                QMessageBox.critical(self, 'Error', f'Failed to load file: {str(e)}')

    def clear_tracks(self):
        """Clear all loaded tracks and reset the display."""
        self.engine.clear_tracks()
        self.waveform.zoom_level = 1.0
        self.waveform.view_start_time = 0.0
        self.waveform.view_end_time = 0.0
        self.waveform.set_waveform([], 0.0, 2, [])
        self.statusBar().showMessage('All tracks cleared')

    def update_waveform(self):
        """
        Request waveform data from engine and update display.

        Automatically adjusts resolution based on zoom level and
        visible time range. Handles multiple tracks.
        """
        try:
            if not hasattr(self, 'engine'):
                return

            duration = self.engine.get_duration()
            if duration == 0:
                return

            channels = self.engine.get_channels()
            track_info = self.engine.get_track_info()

            width = self.waveform.width()
            if width <= 0:
                return

            waveform_data = self.engine.get_waveform_for_range(
                self.waveform.view_start_time,
                self.waveform.view_end_time,
                width
            )

            self.waveform.set_waveform(waveform_data, duration, channels, track_info)
        except Exception as e:
            print(f"Error updating waveform: {e}")

    def play(self):
        """
        Start or resume audio playback.

        If a region is selected, plays only that region. Resumes from
        current position if paused within a selection, otherwise restarts
        from the beginning of the selection or file.
        """
        try:
            selection = self.waveform.get_selection()
            current_pos = self.engine.get_playback_position()

            if selection:
                (start, end), track_indices = selection
                if current_pos < start or current_pos >= end:
                    self.engine.stop()
                    self.engine.play(start, end)
                else:
                    self.engine.play(None, None)
            else:
                if 0 < current_pos < self.engine.get_duration():
                    self.engine.play(None, None)
                else:
                    self.engine.stop()
                    self.engine.play(None, None)
        except Exception as e:
            QMessageBox.critical(self, 'Error', f'Playback error: {str(e)}')

    def pause(self):
        """Pause audio playback without resetting position."""
        self.engine.pause()

    def rewind(self):
        """Stop playback and return to the beginning."""
        self.engine.stop()
        self.waveform.clear_playback_position()

    def skip_to_end(self):
        """Stop playback and move cursor to the end of the audio."""
        try:
            self.engine.stop()
            duration = self.engine.get_duration()
            self.waveform.set_playback_position(duration)
        except Exception as e:
            print(f"Error skipping: {e}")

    def toggle_repeat(self):
        """Toggle repeat mode for continuous playback."""
        self.is_repeating = self.repeat_btn.isChecked()
        status = "On" if self.is_repeating else "Off"
        self.repeat_btn.setText(f'🔁 Repeat: {status}')

    def toggle_playback(self):
        """
        Toggle between play and pause states.

        Intelligently handles restarting from beginning if at the end
        of a selection or file.
        """
        try:
            if self.engine.is_playing():
                self.pause()
            else:
                position = self.engine.get_playback_position()
                selection = self.waveform.get_selection()

                if selection:
                    (start, end), track_indices = selection
                    if position >= end:
                        self.engine.stop()
                        self.engine.play(start, end)
                    else:
                        self.play()
                else:
                    duration = self.engine.get_duration()
                    if position >= duration:
                        self.engine.stop()
                        self.engine.play(None, None)
                    else:
                        self.play()
        except Exception as e:
            print(f"Error toggling playback: {e}")

    def _handle_playback_end(self, selection, position, end_position):
        """
        Handle playback reaching the end of selection or file.

        Parameters
        ----------
        selection : tuple or None
            current selection range
        position : float
            current playback position
        end_position : float
            end position (selection end or duration)

        Returns
        -------
        bool
            True if playback should repeat
        """
        if position >= end_position - 0.05:
            if self.is_repeating:
                return True
            else:
                self.engine.stop()
                self.waveform.set_playback_position(end_position)
        return False

    def check_playback(self):
        """
        Update playback position and handle repeat mode.

        Called periodically by timer to update UI and detect when
        playback reaches the end of a selection or file.
        """
        try:
            if self.engine.is_playing():
                position = self.engine.get_playback_position()
                self.waveform.set_playback_position(position)

                # check if we've reached the end of selection/file
                selection = self.waveform.get_selection()
                duration = self.engine.get_duration()

                if selection:
                    (start, end), track_indices = selection
                    should_repeat = self._handle_playback_end(selection, position, end)
                    if should_repeat:
                        self.engine.stop()
                        self.engine.play(start, end)
                        self.waveform.set_playback_position(start)
                else:
                    should_repeat = self._handle_playback_end(None, position, duration)
                    if should_repeat:
                        self.engine.stop()
                        self.engine.play(None, None)
                        self.waveform.set_playback_position(0)

        except Exception as e:
            print(f"Error checking playback: {e}")

    def delete_region(self):
        """
        Delete the currently selected audio region from selected tracks only.

        Positions the playback cursor at the start of the deleted region
        and updates the waveform display.
        """
        selection = self.waveform.get_selection()
        if selection:
            try:
                (start, end), track_indices = selection
                self.engine.delete_region(start, end, list(track_indices))
                self.waveform.clear_selection()

                self.engine.set_playback_position(start)
                self.waveform.set_playback_position(start)

                self.update_waveform()
                track_str = ", ".join(str(i + 1) for i in sorted(track_indices))
                self.statusBar().showMessage(f'Deleted region: {start:.2f}s - {end:.2f}s from track(s) {track_str}')
            except Exception as e:
                QMessageBox.critical(self, 'Error', f'Delete error: {str(e)}')

    def export_file(self, file_type='wav'):
        """
        Export mixed audio to a file with optional format-specific settings.

        Parameters
        ----------
        file_type : str
            output format ('wav', 'flac', or 'mp3')

        Notes
        -----
        Shows a dialog for FLAC/MP3 options before the save dialog.
        Exports the selection if one exists, otherwise exports entire file.
        All tracks are mixed together for export.
        """
        try:
            compression_level = None
            bitrate = None

            # show options dialog first for FLAC and MP3
            if file_type in ['flac', 'mp3']:
                dialog = ExportDialog(self, file_type)
                if dialog.exec() != QDialog.DialogCode.Accepted:
                    return

                if file_type == 'flac':
                    compression_level = dialog.get_compression_level()
                elif file_type == 'mp3':
                    bitrate = dialog.get_bitrate()

            track_info = self.engine.get_track_info()
            has_stereo = any(info[2] == 2 for info in track_info)
            num_mono = sum(1 for info in track_info if info[2] == 1)

            if has_stereo or num_mono >= 2:
                channel_dialog = ChannelExportDialog(self, has_stereo, num_mono)
                if channel_dialog.exec() != QDialog.DialogCode.Accepted:
                    return
                channel_mode = channel_dialog.get_channel_mode()

            filter_map = {
                'wav': "WAV Files (*.wav)",
                'flac': "FLAC Files (*.flac)",
                'mp3': "MP3 Files (*.mp3)"
            }

            # then show file save dialog
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                f"Export as {file_type.upper()}",
                "",
                filter_map.get(file_type, "All Files (*)")
            )

            if not file_path:
                return

            # add extension if not present
            if not file_path.lower().endswith(f'.{file_type}'):
                file_path += f'.{file_type}'

            selection = self.waveform.get_selection()
            if selection:
                (start, end), track_indices = selection
                self.engine.export_audio(file_path, start, end, compression_level, bitrate, channel_mode)
                self.statusBar().showMessage(f'Exported selection: {file_path}')
            else:
                self.engine.export_audio(file_path, 0.0, self.engine.get_duration(),
                                         compression_level, bitrate, channel_mode)
                self.statusBar().showMessage(f'Exported entire file: {file_path}')

        except Exception as e:
            QMessageBox.critical(self, 'Error', f'Export error: {str(e)}')

    def resizeEvent(self, event):
        """
        Handle window resize events.

        Parameters
        ----------
        event : QResizeEvent
            resize event details

        Notes
        -----
        Triggers waveform update to adjust resolution for new window size.
        """
        super().resizeEvent(event)
        if hasattr(self, 'engine'):
            self.update_waveform()


def main():
    """Application entry point."""
    app = QApplication(sys.argv)
    window = AudioEditorWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()