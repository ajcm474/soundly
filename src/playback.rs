use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
use cpal::{Stream, StreamConfig};
use std::sync::{Arc, Mutex};

struct PlaybackState
{
    buffer: Vec<f32>,
    position: usize,
    is_playing: bool,
    is_paused: bool,
    start_time_offset: f64,
}

pub struct AudioPlayback
{
    state: Arc<Mutex<PlaybackState>>,
    _stream: Stream,
    sample_rate: u32,
    channels: usize,
}

impl AudioPlayback
{
    pub fn new(sample_rate: u32, channels: usize) -> Result<Self, String>
    {
        let host = cpal::default_host();
        let device = host
            .default_output_device()
            .ok_or("No output device available")?;

        let config = StreamConfig
        {
            channels: channels as u16,
            sample_rate: cpal::SampleRate(sample_rate),
            buffer_size: cpal::BufferSize::Default,
        };

        let state = Arc::new(Mutex::new(PlaybackState
        {
            buffer: Vec::new(),
            position: 0,
            is_playing: false,
            is_paused: false,
            start_time_offset: 0.0,
        }));

        let state_clone = state.clone();

        let stream = device
            .build_output_stream(
                &config,
                move |data: &mut [f32], _: &cpal::OutputCallbackInfo|
                {
                    let mut state = state_clone.lock().unwrap();

                    for sample in data.iter_mut()
                    {
                        if state.is_playing && state.position < state.buffer.len()
                        {
                            *sample = state.buffer[state.position];
                            state.position += 1;
                        }
                        else
                        {
                            *sample = 0.0;
                            if state.position >= state.buffer.len()
                            {
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

        Ok(AudioPlayback
        {
            state,
            _stream: stream,
            sample_rate,
            channels,
        })
    }

    pub fn play(&mut self, buffer: Vec<f32>, start_time_offset: f64) -> Result<(), String>
    {
        let mut state = self.state.lock().unwrap();
        state.buffer = buffer;
        state.position = 0;
        state.is_playing = true;
        state.is_paused = false;
        state.start_time_offset = start_time_offset;
        Ok(())
    }

    pub fn resume(&mut self) -> Result<(), String>
    {
        let mut state = self.state.lock().unwrap();
        if state.is_paused && !state.buffer.is_empty()
        {
            state.is_playing = true;
            state.is_paused = false;
        }
        Ok(())
    }

    pub fn pause(&mut self)
    {
        let mut state = self.state.lock().unwrap();
        if state.is_playing
        {
            state.is_playing = false;
            state.is_paused = true;
        }
    }

    pub fn stop(&mut self)
    {
        let mut state = self.state.lock().unwrap();
        state.is_playing = false;
        state.is_paused = false;
        state.position = 0;
        state.start_time_offset = 0.0;
    }

    pub fn is_playing(&self) -> bool
    {
        self.state.lock().unwrap().is_playing
    }

    pub fn is_paused(&self) -> bool
    {
        self.state.lock().unwrap().is_paused
    }

    pub fn get_position(&self) -> f64
    {
        let state = self.state.lock().unwrap();
        let current_sample = state.position / self.channels;
        let current_time = current_sample as f64 / self.sample_rate as f64;
        current_time + state.start_time_offset
    }

    pub fn set_position(&mut self, position: f64)
    {
        let mut state = self.state.lock().unwrap();
        let sample_position = (position * self.sample_rate as f64) as usize * self.channels;
        state.position = sample_position.min(state.buffer.len());
    }
}