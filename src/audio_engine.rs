use symphonia::core::audio::{AudioBufferRef, Signal};
use symphonia::core::codecs::{DecoderOptions, CODEC_TYPE_NULL};
use symphonia::core::formats::FormatOptions;
use symphonia::core::io::MediaSourceStream;
use symphonia::core::meta::MetadataOptions;
use symphonia::core::probe::Hint;
use std::fs::File;
use std::path::Path;
use crate::playback::AudioPlayback;

pub struct AudioEngine {
    audio_data: Vec<f32>,
    sample_rate: u32,
    channels: usize,
    playback: Option<AudioPlayback>,
}

impl AudioEngine {
    pub fn new() -> Self {
        AudioEngine {
            audio_data: Vec::new(),
            sample_rate: 44100,
            channels: 2,
            playback: None,
        }
    }

    pub fn load_file(&mut self, path: &str) -> Result<(), String> {
        let file = File::open(path).map_err(|e| e.to_string())?;
        let mss = MediaSourceStream::new(Box::new(file), Default::default());

        let mut hint = Hint::new();
        if let Some(ext) = Path::new(path).extension() {
            hint.with_extension(ext.to_str().unwrap_or(""));
        }

        let meta_opts: MetadataOptions = Default::default();
        let fmt_opts: FormatOptions = Default::default();

        let probed = symphonia::default::get_probe()
            .format(&hint, mss, &fmt_opts, &meta_opts)
            .map_err(|e| format!("Probe error: {}", e))?;

        let mut format = probed.format;
        let track = format
            .tracks()
            .iter()
            .find(|t| t.codec_params.codec != CODEC_TYPE_NULL)
            .ok_or("No valid audio track found")?;

        let dec_opts: DecoderOptions = Default::default();
        let mut decoder = symphonia::default::get_codecs()
            .make(&track.codec_params, &dec_opts)
            .map_err(|e| format!("Decoder error: {}", e))?;

        self.sample_rate = track.codec_params.sample_rate.unwrap_or(44100);
        self.channels = track.codec_params.channels.unwrap_or_default().count();
        self.audio_data.clear();

        loop {
            let packet = match format.next_packet() {
                Ok(packet) => packet,
                Err(_) => break,
            };

            match decoder.decode(&packet) {
                Ok(audio_buf) => {
                    self.append_audio_buffer(audio_buf);
                }
                Err(_) => continue,
            }
        }

        Ok(())
    }

    fn append_audio_buffer(&mut self, audio_buf: AudioBufferRef) {
        match audio_buf {
            AudioBufferRef::F32(buf) => {
                for frame in 0..buf.frames() {
                    for ch in 0..buf.spec().channels.count() {
                        self.audio_data.push(buf.chan(ch)[frame]);
                    }
                }
            }
            AudioBufferRef::S32(buf) => {
                for frame in 0..buf.frames() {
                    for ch in 0..buf.spec().channels.count() {
                        self.audio_data.push(buf.chan(ch)[frame] as f32 / i32::MAX as f32);
                    }
                }
            }
            AudioBufferRef::S16(buf) => {
                for frame in 0..buf.frames() {
                    for ch in 0..buf.spec().channels.count() {
                        self.audio_data.push(buf.chan(ch)[frame] as f32 / i16::MAX as f32);
                    }
                }
            }
            _ => {}
        }
    }

    pub fn get_waveform_data(&self, samples_per_pixel: usize) -> Vec<(f32, f32)> {
        if self.audio_data.is_empty() {
            return Vec::new();
        }

        let frame_count = self.audio_data.len() / self.channels;
        let pixel_count = (frame_count + samples_per_pixel - 1) / samples_per_pixel;
        let mut waveform = Vec::with_capacity(pixel_count);

        for i in 0..pixel_count {
            let start = i * samples_per_pixel * self.channels;
            let end = ((i + 1) * samples_per_pixel * self.channels).min(self.audio_data.len());

            let mut min = 0.0f32;
            let mut max = 0.0f32;

            for &sample in &self.audio_data[start..end] {
                min = min.min(sample);
                max = max.max(sample);
            }

            waveform.push((min, max));
        }

        waveform
    }

    pub fn get_sample_rate(&self) -> u32 {
        self.sample_rate
    }

    pub fn get_duration(&self) -> f64 {
        if self.audio_data.is_empty() {
            return 0.0;
        }
        (self.audio_data.len() / self.channels) as f64 / self.sample_rate as f64
    }

    pub fn play(&mut self, start_time: Option<f64>, end_time: Option<f64>) -> Result<(), String> {
        let start_frame = start_time.map(|t| (t * self.sample_rate as f64) as usize).unwrap_or(0);
        let end_frame = end_time
            .map(|t| (t * self.sample_rate as f64) as usize)
            .unwrap_or(self.audio_data.len() / self.channels);

        let start_sample = start_frame * self.channels;
        let end_sample = end_frame * self.channels;

        let audio_slice = &self.audio_data[start_sample..end_sample.min(self.audio_data.len())];

        if self.playback.is_none() {
            self.playback = Some(AudioPlayback::new(self.sample_rate, self.channels)?);
        }

        if let Some(ref mut playback) = self.playback {
            playback.play(audio_slice.to_vec())?;
        }

        Ok(())
    }

    pub fn pause(&mut self) {
        if let Some(ref mut playback) = self.playback {
            playback.pause();
        }
    }

    pub fn stop(&mut self) {
        if let Some(ref mut playback) = self.playback {
            playback.stop();
        }
    }

    pub fn is_playing(&self) -> bool {
        self.playback.as_ref().map(|p| p.is_playing()).unwrap_or(false)
    }

    pub fn get_playback_position(&self) -> f64 {
        self.playback
            .as_ref()
            .map(|p| p.get_position())
            .unwrap_or(0.0)
    }

    pub fn set_playback_position(&mut self, position: f64) {
        if let Some(ref mut playback) = self.playback {
            playback.set_position(position);
        }
    }

    pub fn delete_region(&mut self, start_time: f64, end_time: f64) -> Result<(), String> {
        let start_frame = (start_time * self.sample_rate as f64) as usize;
        let end_frame = (end_time * self.sample_rate as f64) as usize;

        let start_sample = start_frame * self.channels;
        let end_sample = end_frame * self.channels;

        if start_sample >= self.audio_data.len() {
            return Err("Start position out of bounds".to_string());
        }

        let end_sample = end_sample.min(self.audio_data.len());
        self.audio_data.drain(start_sample..end_sample);

        Ok(())
    }

    pub fn export_audio(&self, path: &str, start_time: Option<f64>, end_time: Option<f64>) -> Result<(), String> {
        let start_frame = start_time.map(|t| (t * self.sample_rate as f64) as usize).unwrap_or(0);
        let end_frame = end_time
            .map(|t| (t * self.sample_rate as f64) as usize)
            .unwrap_or(self.audio_data.len() / self.channels);

        let start_sample = start_frame * self.channels;
        let end_sample = (end_frame * self.channels).min(self.audio_data.len());

        let export_data = &self.audio_data[start_sample..end_sample];

        let path_lower = path.to_lowercase();
        if path_lower.ends_with(".wav") {
            self.export_wav(path, export_data)?;
        } else if path_lower.ends_with(".flac") {
            self.export_flac(path, export_data)?;
        } else if path_lower.ends_with(".mp3") {
            self.export_mp3(path, export_data)?;
        } else {
            return Err("Unsupported format. Use .wav, .flac, or .mp3".to_string());
        }

        Ok(())
    }

    fn export_wav(&self, path: &str, data: &[f32]) -> Result<(), String> {
        let spec = hound::WavSpec {
            channels: self.channels as u16,
            sample_rate: self.sample_rate,
            bits_per_sample: 16,
            sample_format: hound::SampleFormat::Int,
        };

        let mut writer = hound::WavWriter::create(path, spec)
            .map_err(|e| format!("Failed to create WAV file: {}", e))?;

        for &sample in data {
            let sample_i16 = (sample * i16::MAX as f32) as i16;
            writer.write_sample(sample_i16)
                .map_err(|e| format!("Failed to write sample: {}", e))?;
        }

        writer.finalize()
            .map_err(|e| format!("Failed to finalize WAV: {}", e))?;

        Ok(())
    }

    fn export_flac(&self, path: &str, data: &[f32]) -> Result<(), String> {
        // Simplified FLAC export - convert to WAV for now
        // For full FLAC support, use a proper FLAC encoder
        self.export_wav(path, data)
    }

    fn export_mp3(&self, path: &str, data: &[f32]) -> Result<(), String> {
        // Simplified MP3 export - convert to WAV for now
        // For full MP3 support, use mp3lame-encoder properly
        self.export_wav(path, data)
    }
}