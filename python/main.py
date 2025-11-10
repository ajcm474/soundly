import sys
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QPushButton, QFileDialog, QMessageBox,
                             QDialog, QComboBox, QLabel, QDialogButtonBox)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QKeySequence, QShortcut
from waveform_widget import WaveformWidget
import soundly


class ExportDialog(QDialog):
    def __init__(self, parent=None, file_type="wav"):
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
            self.compression_combo.setCurrentIndex(5)  # Default to 5
            layout.addWidget(self.compression_combo)

        elif file_type == "mp3":
            layout.addWidget(QLabel("Bitrate:"))
            self.bitrate_combo = QComboBox()
            self.bitrate_combo.addItems([
                "128 kbps",
                "160 kbps",
                "192 kbps",
                "256 kbps",
                "320 kbps"
            ])
            self.bitrate_combo.setCurrentIndex(2)  # Default to 192
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
        if self.file_type == "flac":
            return self.compression_combo.currentIndex()
        return None

    def get_bitrate(self):
        if self.file_type == "mp3":
            text = self.bitrate_combo.currentText()
            return int(text.split()[0])
        return None


class AudioEditorWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.engine = soundly.AudioEditor()
        self.is_repeating = False
        self.playback_timer = QTimer()
        self.playback_timer.timeout.connect(self.check_playback)
        self.playback_timer.start(50)  # Check every 50ms

        self.init_ui()

    def init_ui(self):
        self.setWindowTitle('Audio Editor')
        self.setGeometry(100, 100, 1200, 600)

        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Main layout
        main_layout = QVBoxLayout(central_widget)

        # Button layout
        button_layout = QHBoxLayout()

        # Create buttons
        self.import_btn = QPushButton('Import')
        self.import_btn.clicked.connect(self.import_file)

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

        self.export_btn = QPushButton('Export')
        self.export_btn.clicked.connect(self.export_file)

        # Add buttons to layout
        button_layout.addWidget(self.import_btn)
        button_layout.addWidget(self.rewind_btn)
        button_layout.addWidget(self.play_btn)
        button_layout.addWidget(self.pause_btn)
        button_layout.addWidget(self.skip_btn)
        button_layout.addWidget(self.repeat_btn)
        button_layout.addStretch()
        button_layout.addWidget(self.export_btn)

        # Waveform widget
        self.waveform = WaveformWidget()

        # Add to main layout
        main_layout.addLayout(button_layout)
        main_layout.addWidget(self.waveform)

        # Keyboard shortcuts
        self.setup_shortcuts()

    def setup_shortcuts(self):
        # Zoom shortcuts - Fixed to handle + key properly
        zoom_in = QShortcut(QKeySequence('Ctrl+='), self)
        zoom_in.activated.connect(self.waveform.zoom_in)

        # Also support Ctrl+Plus for zoom in
        zoom_in_plus = QShortcut(QKeySequence.StandardKey.ZoomIn, self)
        zoom_in_plus.activated.connect(self.waveform.zoom_in)

        zoom_out = QShortcut(QKeySequence('Ctrl+-'), self)
        zoom_out.activated.connect(self.waveform.zoom_out)

        # Delete shortcuts
        delete = QShortcut(QKeySequence(Qt.Key.Key_Delete), self)
        delete.activated.connect(self.delete_region)

        backspace = QShortcut(QKeySequence(Qt.Key.Key_Backspace), self)
        backspace.activated.connect(self.delete_region)

        # Playback shortcuts
        space = QShortcut(QKeySequence(Qt.Key.Key_Space), self)
        space.activated.connect(self.toggle_playback)

    def import_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Audio File",
            "",
            "Audio Files (*.wav *.flac *.mp3);;All Files (*)"
        )

        if file_path:
            try:
                self.engine.load_file(file_path)
                self.update_waveform()
                self.statusBar().showMessage(f'Loaded: {file_path}')
            except Exception as e:
                QMessageBox.critical(self, 'Error', f'Failed to load file: {str(e)}')

    def update_waveform(self):
        try:
            width = self.waveform.width()
            samples_per_pixel = max(1, int(self.engine.get_sample_rate() *
                                           self.engine.get_duration() /
                                           width / self.waveform.zoom_level))
            waveform_data = self.engine.get_waveform_data(samples_per_pixel)
            self.waveform.set_waveform(waveform_data, self.engine.get_duration())
        except Exception as e:
            print(f"Error updating waveform: {e}")

    def play(self):
        try:
            selection = self.waveform.get_selection()
            current_pos = self.engine.get_playback_position()

            if selection:
                start, end = selection
                # Only restart from beginning of selection if we're outside the selection
                # or at the end of the selection
                if current_pos < start or current_pos >= end:
                    self.engine.stop()
                    self.engine.play(start, end)
                else:
                    # Resume from current position within selection
                    self.engine.play(None, None)
            else:
                # Resume from current position or start from beginning
                if current_pos > 0 and current_pos < self.engine.get_duration():
                    # Resume from current position
                    self.engine.play(None, None)
                else:
                    # Start from beginning
                    self.engine.stop()
                    self.engine.play(None, None)
        except Exception as e:
            QMessageBox.critical(self, 'Error', f'Playback error: {str(e)}')

    def pause(self):
        self.engine.pause()

    def rewind(self):
        self.engine.stop()
        self.waveform.clear_playback_position()

    def skip_to_end(self):
        try:
            # Stop playback first
            self.engine.stop()
            # Set cursor to end
            duration = self.engine.get_duration()
            self.waveform.set_playback_position(duration)
        except Exception as e:
            print(f"Error skipping: {e}")

    def toggle_repeat(self):
        self.is_repeating = self.repeat_btn.isChecked()
        status = "On" if self.is_repeating else "Off"
        self.repeat_btn.setText(f'🔁 Repeat: {status}')

    def toggle_playback(self):
        try:
            if self.engine.is_playing():
                self.pause()
            else:
                # When resuming, check if we need to restart
                position = self.engine.get_playback_position()
                selection = self.waveform.get_selection()

                if selection:
                    start, end = selection
                    # If we're at the end of selection, restart from beginning
                    if position >= end:
                        self.engine.stop()
                        self.engine.play(start, end)
                    else:
                        self.play()
                else:
                    # If we're at the end of file, restart from beginning
                    duration = self.engine.get_duration()
                    if position >= duration:
                        self.engine.stop()
                        self.engine.play(None, None)
                    else:
                        self.play()
        except Exception as e:
            print(f"Error toggling playback: {e}")

    def check_playback(self):
        try:
            if self.engine.is_playing():
                position = self.engine.get_playback_position()
                self.waveform.set_playback_position(position)

                # Check if we've reached the end of selection/file
                selection = self.waveform.get_selection()
                if selection:
                    start, end = selection
                    if position >= end:
                        if self.is_repeating:
                            # Stop and restart from selection beginning
                            self.engine.stop()
                            self.engine.play(start, end)
                            self.waveform.set_playback_position(start)
                        else:
                            self.engine.stop()
                            self.waveform.set_playback_position(end)
                else:
                    duration = self.engine.get_duration()
                    if position >= duration:
                        if self.is_repeating:
                            # Stop and restart from beginning
                            self.engine.stop()
                            self.engine.play(None, None)
                            self.waveform.set_playback_position(0)
                        else:
                            self.engine.stop()
                            self.waveform.set_playback_position(duration)
        except Exception as e:
            print(f"Error checking playback: {e}")

    def delete_region(self):
        selection = self.waveform.get_selection()
        if selection:
            try:
                start, end = selection
                self.engine.delete_region(start, end)
                self.waveform.clear_selection()
                self.update_waveform()
                self.statusBar().showMessage(f'Deleted region: {start:.2f}s - {end:.2f}s')
            except Exception as e:
                QMessageBox.critical(self, 'Error', f'Delete error: {str(e)}')

    def export_file(self):
        file_path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export Audio File",
            "",
            "WAV Files (*.wav);;FLAC Files (*.flac);;MP3 Files (*.mp3)"
        )

        if file_path:
            try:
                # Determine file type
                file_type = "wav"
                if file_path.lower().endswith('.flac'):
                    file_type = "flac"
                elif file_path.lower().endswith('.mp3'):
                    file_type = "mp3"

                compression_level = None
                bitrate = None

                # Show options dialog for FLAC and MP3
                if file_type in ["flac", "mp3"]:
                    dialog = ExportDialog(self, file_type)
                    if dialog.exec() == QDialog.DialogCode.Accepted:
                        if file_type == "flac":
                            compression_level = dialog.get_compression_level()
                        elif file_type == "mp3":
                            bitrate = dialog.get_bitrate()
                    else:
                        return  # User cancelled

                selection = self.waveform.get_selection()
                if selection:
                    start, end = selection
                    self.engine.export_audio(file_path, start, end,
                                             compression_level, bitrate)
                    self.statusBar().showMessage(f'Exported selection: {file_path}')
                else:
                    # Export entire file when no selection
                    self.engine.export_audio(file_path, 0.0, self.engine.get_duration(),
                                             compression_level, bitrate)
                    self.statusBar().showMessage(f'Exported entire file: {file_path}')
            except Exception as e:
                QMessageBox.critical(self, 'Error', f'Export error: {str(e)}')

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'engine'):
            self.update_waveform()


def main():
    app = QApplication(sys.argv)
    window = AudioEditorWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()