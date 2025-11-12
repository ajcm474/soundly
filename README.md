# Soundly Audio Editor
A fast, lightweight audio editor built with Rust and Python, 
featuring real-time waveform visualization and support for multiple audio formats.

## Features
- **Multi-format support**: Import and export WAV, FLAC, and MP3 files
- **Real-time waveform visualization**: Zoom in to individual samples or zoom out to see hours of audio
- **Region-based editing**: Select and delete audio regions with visual feedback
- **Playback controls**: Play, pause, repeat, and navigate through audio
- **High-quality export**: Configurable compression for FLAC (0-8) and bitrate for MP3 (128-320 kbps)
- **Pure Rust FLAC encoder**: Custom implementation based on RFC 9639

## Building

### Prerequisites
* Python 3.8 or higher
* Rust toolchain (install from rustup.rs)
* PyQt6 and NumPy (installed automatically by maturin)

### Build Steps
1. Clone the repository:
```bash
git clone https://github.com/ajcm474/soundly
cd soundly
```

2.  Build and install using maturin:
```bash
pip install maturin
maturin develop --release
```

Or build a wheel for distribution:
```bash
maturin build --release
pip install target/wheels/soundly-*.whl
```

## Running
After building, run the application:
```bash
python python/main.py
```

## Usage

### Importing Audio
- `File` → `Import` → `Audio File...` to import WAV, FLAC, or MP3 files
- Supported sample rates: 8 kHz to 192 kHz
- Supported channel configurations: Mono and Stereo

### Playback
- **Space**: Toggle play/pause
- **Play button**: Start or resume playback
- **Pause button**: Pause playback
- **⏮ Rewind**: Stop and return to beginning
- **Skip ⏭**: Jump to the end
- **🔁 Repeat**: Toggle repeat mode for continuous playback

### Editing
- **Click and drag**: Select a region of audio
- **Delete/Backspace**: Remove the selected region
- The playback cursor shows the current position

### Zooming
- **Ctrl/Cmd + Plus**: Zoom in (can zoom down to individual samples)
- **Ctrl/Cmd + Minus**: Zoom out
- **Mouse wheel**: Zoom in/out centered on mouse position
- Auto-scrolling follows playback when zoomed in

### Exporting
- `File` → `Export` → `WAV...`: Export as uncompressed WAV
- `File` → `Export` → `FLAC...`: Export with configurable compression (0=fastest, 8=best compression)
- `File` → `Export` → `MP3...`: Export with configurable bitrate (128-320 kbps)
- Exports the selected region if one exists, otherwise exports the entire file

## Current Limitations
- **Undo/Redo**: Not yet implemented - edits are permanent
- **Multi-track**: Single track only (stereo or mono)
- **Effects**: No audio effects or filters currently available
- **Selection precision**: Minimum selection size is 1ms
- **FLAC encoder**: Custom implementation supports compression levels 0-8 but may be less efficient
- **Memory usage**: Entire audio file is loaded into memory (not suitable for very large files >1GB)
- **Sample rate conversion**: Not supported - export uses the same sample rate as the source
- **Bit depth**: Internal processing uses 32-bit float; export is 16-bit for all formats

## Keyboard Shortcuts
- **Space**: Toggle play/pause
- **Delete/Backspace**: Delete selected region
- **Ctrl/Cmd + =**: Zoom in
- **Ctrl/Cmd + -**: Zoom out
- **Ctrl/Cmd + Q**: Quit application

## Architecture
The project uses a hybrid architecture:

- **Rust core** (`src/`): Audio decoding, encoding, playback engine, and DSP operations
- **Python GUI** (`python/`): PyQt6-based user interface and visualization
- **PyO3 bindings**: Zero-copy data transfer between Rust and Python

This design provides native performance for audio operations while maintaining a flexible, easy-to-modify GUI.

## License
This project is released under the Apache 2.0 License. See [LICENSE](LICENSE) for details.