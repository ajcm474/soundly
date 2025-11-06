import sys
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QPushButton, QFileDialog, QMessageBox)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QKeySequence, QShortcut
from waveform_widget import WaveformWidget
import soundly


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
        # Zoom shortcuts
        zoom_in = QShortcut(QKeySequence('Ctrl++'), self)
        zoom_in.activated.connect(self.waveform.zoom_in)

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
            if selection:
                start, end = selection
                self.engine.play(start, end)
            else:
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
            duration = self.engine.get_duration()
            self.engine.set_playback_position(duration)
            self.engine.stop()
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
                self.play()
        except Exception as e:
            print(f"Error toggling playback: {e}")

    def check_playback(self):
        try:
            if self.engine.is_playing():
                position = self.engine.get_playback_position()
                self.waveform.set_playback_position(position)
            else:
                # Check if we should repeat
                if self.is_repeating and self.waveform.playback_position > 0:
                    self.play()
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
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Audio File",
            "",
            "WAV Files (*.wav);;FLAC Files (*.flac);;MP3 Files (*.mp3)"
        )

        if file_path:
            try:
                selection = self.waveform.get_selection()
                if selection:
                    start, end = selection
                    self.engine.export_audio(file_path, start, end)
                else:
                    self.engine.export_audio(file_path, None, None)
                self.statusBar().showMessage(f'Exported: {file_path}')
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