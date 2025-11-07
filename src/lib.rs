use pyo3::prelude::*;
use pyo3::exceptions::PyRuntimeError;
use std::sync::{Arc, Mutex};

mod audio_engine;
mod playback;

use audio_engine::AudioEngine;

#[pyclass(unsendable)]
struct AudioEditor {
    engine: Arc<Mutex<AudioEngine>>,
}

#[pymethods]
impl AudioEditor {
    #[new]
    fn new() -> PyResult<Self> {
        Ok(AudioEditor {
            engine: Arc::new(Mutex::new(AudioEngine::new())),
        })
    }

    fn load_file(&mut self, path: String) -> PyResult<()> {
        self.engine
            .lock()
            .unwrap()
            .load_file(&path)
            .map_err(|e| PyRuntimeError::new_err(format!("Failed to load file: {}", e)))
    }

    fn get_waveform_data(&self, samples_per_pixel: usize) -> PyResult<Vec<(f32, f32)>> {
        Ok(self.engine.lock().unwrap().get_waveform_data(samples_per_pixel))
    }

    fn get_sample_rate(&self) -> PyResult<u32> {
        Ok(self.engine.lock().unwrap().get_sample_rate())
    }

    fn get_duration(&self) -> PyResult<f64> {
        Ok(self.engine.lock().unwrap().get_duration())
    }

    fn play(&mut self, start_time: Option<f64>, end_time: Option<f64>) -> PyResult<()> {
        self.engine
            .lock()
            .unwrap()
            .play(start_time, end_time)
            .map_err(|e| PyRuntimeError::new_err(format!("Playback error: {}", e)))
    }

    fn pause(&mut self) -> PyResult<()> {
        self.engine.lock().unwrap().pause();
        Ok(())
    }

    fn stop(&mut self) -> PyResult<()> {
        self.engine.lock().unwrap().stop();
        Ok(())
    }

    fn is_playing(&self) -> PyResult<bool> {
        Ok(self.engine.lock().unwrap().is_playing())
    }

    fn get_playback_position(&self) -> PyResult<f64> {
        Ok(self.engine.lock().unwrap().get_playback_position())
    }

    fn set_playback_position(&mut self, position: f64) -> PyResult<()> {
        self.engine.lock().unwrap().set_playback_position(position);
        Ok(())
    }

    fn delete_region(&mut self, start_time: f64, end_time: f64) -> PyResult<()> {
        self.engine
            .lock()
            .unwrap()
            .delete_region(start_time, end_time)
            .map_err(|e| PyRuntimeError::new_err(format!("Delete error: {}", e)))
    }

    #[pyo3(signature = (path, start_time=None, end_time=None, compression_level=None, bitrate_kbps=None))]
    fn export_audio(&self, path: String, start_time: Option<f64>, end_time: Option<f64>,
                    compression_level: Option<u8>, bitrate_kbps: Option<u32>) -> PyResult<()> {
        self.engine
            .lock()
            .unwrap()
            .export_audio(&path, start_time, end_time, compression_level, bitrate_kbps)
            .map_err(|e| PyRuntimeError::new_err(format!("Export error: {}", e)))
    }
}

#[pymodule]
fn soundly(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_class::<AudioEditor>()?;
    Ok(())
}