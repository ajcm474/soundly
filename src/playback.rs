use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
use cpal::{Stream, StreamConfig};
use std::sync::{Arc, Mutex};

struct PlaybackState {
    buffer: Vec<f32>,
    position: usize,
    is_playing: bool,
    start_time_offset: f64,  // Add offset for proper position tracking
}

pub struct AudioPlayback {
    state: Arc<Mutex<PlaybackState>>,
    _stream: Stream,
    sample_rate: u32,
    channels: usize,
}

impl AudioPlayback {
    pub fn new(sample_rate: u32, channels: usize) -> Result<Self, String> {
        let host = cpal::default_host();
        let device = host
            .default_output_device()
            .ok_or("No output device available")?;

        let config = StreamConfig {
            channels: channels as u16,
            sample_rate: cpal::SampleRate(sample_rate),
            buffer_size: cpal::BufferSize::Default,
        };

        let state = Arc::new(Mutex::new(PlaybackState {
            buffer: Vec::new(),
            position: 0,
            is_playing: false,
            start_time_offset: 0.0,
        }));

        let state_clone = state.clone();
        let channels = channels;

        let stream = device
            .build_output_stream(
                &config,
                move |data: &mut [f32], _: &cpal::OutputCallbackInfo| {
                    let mut state = state_clone.lock().unwrap();

                    for sample in data.iter_mut() {
                        if state.is_playing && state.position < state.buffer.len() {
                            *sample = state.buffer[state.position];
                            state.position += 1;
                        } else {
                            *sample = 0.0;
                            if state.position >= state.buffer.len() {
                                state.is_playing = false;
                            }
                        }
                    }
                },
                |err| eprintln!("Audio stream error: {}", err),
                None,
            )
            .map_err(|e| format!("Failed to build stream: {}", e))?;

        stream.play().map_err(|e| format!("Failed to play stream: {}", e))?;

        Ok(AudioPlayback {
            state,
            _stream: stream,
            sample_rate,
            channels,
        })
    }

    pub fn play(&mut self, buffer: Vec<f32>, start_time_offset: f64) -> Result<(), String> {
        let mut state = self.state.lock().unwrap();
        state.buffer = buffer;
        state.position = 0;
        state.is_playing = true;
        state.start_time_offset = start_time_offset;
        Ok(())
    }

    pub fn pause(&mut self) {
        let mut state = self.state.lock().unwrap();
        state.is_playing = false;
    }

    pub fn stop(&mut self) {
        let mut state = self.state.lock().unwrap();
        state.is_playing = false;
        state.position = 0;
        state.start_time_offset = 0.0;
    }

    pub fn is_playing(&self) -> bool {
        self.state.lock().unwrap().is_playing
    }

    pub fn get_position(&self) -> f64 {
        let state = self.state.lock().unwrap();
        let current_sample = state.position / self.channels;
        let current_time = current_sample as f64 / self.sample_rate as f64;
        current_time + state.start_time_offset
    }

    pub fn set_position(&mut self, _position: f64) {
        // Implementation for seeking
    }
}