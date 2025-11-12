use pyo3::prelude::*;
use pyo3::exceptions::PyRuntimeError;
use std::sync::{Arc, Mutex};

mod audio_engine;
mod playback;
mod flac;

use audio_engine::AudioEngine;

/// Python-accessible audio editor class
#[pyclass(unsendable)]
struct AudioEditor
{
    engine: Arc<Mutex<AudioEngine>>,
}

#[pymethods]
impl AudioEditor
{
    /// Create a new audio editor instance
    #[new]
    fn new() -> PyResult<Self>
    {
        Ok(AudioEditor
        {
            engine: Arc::new(Mutex::new(AudioEngine::new())),
        })
    }

    /// Load an audio file from disk
    ///
    /// # Parameters
    /// * `path` - filesystem path to audio file (WAV, FLAC, or MP3)
    ///
    /// # Returns
    /// `PyResult<()>` - Ok if successful
    ///
    /// # Errors
    /// Returns error if file cannot be read or decoded
    fn load_file(&mut self, path: String) -> PyResult<()>
    {
        self.engine
            .lock()
            .unwrap()
            .load_file(&path)
            .map_err(|e| PyRuntimeError::new_err(format!("Failed to load file: {}", e)))
    }

    /// Get waveform data downsampled for display
    ///
    /// # Parameters
    /// * `samples_per_pixel` - number of audio samples to represent per pixel
    ///
    /// # Returns
    /// `Vec<(f32, f32, f32, f32)>` - min/max pairs for left and right channels
    fn get_waveform_data(&self, samples_per_pixel: usize) -> PyResult<Vec<(f32, f32, f32, f32)>>
    {
        Ok(self.engine.lock().unwrap().get_stereo_waveform_data(samples_per_pixel))
    }

    /// Get waveform data for a specific time range
    ///
    /// # Parameters
    /// * `start_time` - start of range in seconds
    /// * `end_time` - end of range in seconds
    /// * `num_pixels` - desired number of data points
    ///
    /// # Returns
    /// `Vec<(f32, f32, f32, f32)>` - waveform data for the range
    ///
    /// # Notes
    /// Automatically switches to individual sample mode when zoomed in far enough
    fn get_waveform_for_range(&self, start_time: f64, end_time: f64, num_pixels: usize) -> PyResult<Vec<(f32, f32, f32, f32)>>
    {
        Ok(self.engine.lock().unwrap().get_waveform_for_range(start_time, end_time, num_pixels))
    }

    /// Get the sample rate of loaded audio
    ///
    /// # Returns
    /// `u32` - sample rate in Hz
    fn get_sample_rate(&self) -> PyResult<u32>
    {
        Ok(self.engine.lock().unwrap().get_sample_rate())
    }

    /// Get the duration of loaded audio
    ///
    /// # Returns
    /// `f64` - duration in seconds
    fn get_duration(&self) -> PyResult<f64>
    {
        Ok(self.engine.lock().unwrap().get_duration())
    }

    /// Get the number of audio channels
    ///
    /// # Returns
    /// `usize` - number of channels (1=mono, 2=stereo)
    fn get_channels(&self) -> PyResult<usize>
    {
        Ok(self.engine.lock().unwrap().get_channels())
    }

    /// Start audio playback
    ///
    /// # Parameters
    /// * `start_time` - optional start time in seconds (None to resume from current position)
    /// * `end_time` - optional end time in seconds (None to play to end)
    ///
    /// # Returns
    /// `PyResult<()>` - Ok if successful
    ///
    /// # Errors
    /// Returns error if playback cannot be started
    fn play(&mut self, start_time: Option<f64>, end_time: Option<f64>) -> PyResult<()>
    {
        self.engine
            .lock()
            .unwrap()
            .play(start_time, end_time)
            .map_err(|e| PyRuntimeError::new_err(format!("Playback error: {}", e)))
    }

    /// Pause audio playback without resetting position
    ///
    /// # Returns
    /// `PyResult<()>` - always Ok
    fn pause(&mut self) -> PyResult<()>
    {
        self.engine.lock().unwrap().pause();
        Ok(())
    }

    /// Stop audio playback and reset position
    ///
    /// # Returns
    /// `PyResult<()>` - always Ok
    fn stop(&mut self) -> PyResult<()>
    {
        self.engine.lock().unwrap().stop();
        Ok(())
    }

    /// Check if audio is currently playing
    ///
    /// # Returns
    /// `bool` - true if playing, false otherwise
    fn is_playing(&self) -> PyResult<bool>
    {
        Ok(self.engine.lock().unwrap().is_playing())
    }

    /// Get current playback position
    ///
    /// # Returns
    /// `f64` - position in seconds
    fn get_playback_position(&self) -> PyResult<f64>
    {
        Ok(self.engine.lock().unwrap().get_playback_position())
    }

    /// Set playback position
    ///
    /// # Parameters
    /// * `position` - new position in seconds
    ///
    /// # Returns
    /// `PyResult<()>` - always Ok
    fn set_playback_position(&mut self, position: f64) -> PyResult<()>
    {
        self.engine.lock().unwrap().set_playback_position(position);
        Ok(())
    }

    /// Delete a region of audio
    ///
    /// # Parameters
    /// * `start_time` - start of region in seconds
    /// * `end_time` - end of region in seconds
    ///
    /// # Returns
    /// `PyResult<()>` - Ok if successful
    ///
    /// # Errors
    /// Returns error if region is invalid
    fn delete_region(&mut self, start_time: f64, end_time: f64) -> PyResult<()>
    {
        self.engine
            .lock()
            .unwrap()
            .delete_region(start_time, end_time)
            .map_err(|e| PyRuntimeError::new_err(format!("Delete error: {}", e)))
    }

    /// Export audio to a file
    ///
    /// # Parameters
    /// * `path` - output file path with extension (.wav, .flac, or .mp3)
    /// * `start_time` - optional start time in seconds (None for beginning)
    /// * `end_time` - optional end time in seconds (None for end)
    /// * `compression_level` - optional FLAC compression level 0-8 (None for default 5)
    /// * `bitrate_kbps` - optional MP3 bitrate in kbps (None for default 192)
    ///
    /// # Returns
    /// `PyResult<()>` - Ok if successful
    ///
    /// # Errors
    /// Returns error if export fails or format is unsupported
    #[pyo3(signature = (path, start_time=None, end_time=None, compression_level=None, bitrate_kbps=None))]
    fn export_audio(&self, path: String, start_time: Option<f64>, end_time: Option<f64>,
                    compression_level: Option<u8>, bitrate_kbps: Option<u32>) -> PyResult<()>
    {
        self.engine
            .lock()
            .unwrap()
            .export_audio(&path, start_time, end_time, compression_level, bitrate_kbps)
            .map_err(|e| PyRuntimeError::new_err(format!("Export error: {}", e)))
    }
}

/// Python module definition
#[pymodule]
fn soundly(_py: Python, m: &PyModule) -> PyResult<()>
{
    m.add_class::<AudioEditor>()?;
    Ok(())
}