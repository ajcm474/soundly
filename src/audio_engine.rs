use symphonia::core::audio::{AudioBufferRef, Signal};
use symphonia::core::codecs::{DecoderOptions, CODEC_TYPE_NULL};
use symphonia::core::formats::FormatOptions;
use symphonia::core::io::MediaSourceStream;
use symphonia::core::meta::MetadataOptions;
use symphonia::core::probe::Hint;
use std::fs::File;
use std::path::Path;
use std::io::Write;
use crate::playback::AudioPlayback;

pub struct AudioEngine
{
    audio_data: Vec<f32>,
    sample_rate: u32,
    channels: usize,
    playback: Option<AudioPlayback>,
}

impl AudioEngine
{
    pub fn new() -> Self
    {
        AudioEngine {
            audio_data: Vec::new(),
            sample_rate: 44100,
            channels: 2,
            playback: None,
        }
    }

    pub fn load_file(&mut self, path: &str) -> Result<(), String>
    {
        let file = File::open(path).map_err(|e| e.to_string())?;
        let mss = MediaSourceStream::new(Box::new(file), Default::default());

        let mut hint = Hint::new();
        if let Some(ext) = Path::new(path).extension()
        {
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

        loop
        {
            let packet = match format.next_packet()
            {
                Ok(packet) => packet,
                Err(_) => break,
            };

            match decoder.decode(&packet)
            {
                Ok(audio_buf) =>
                {
                    self.append_audio_buffer(audio_buf);
                }
                Err(_) => continue,
            }
        }

        // Ensure we have stereo data (convert mono to stereo if needed)
        if self.channels == 1
        {
            let mut stereo_data = Vec::with_capacity(self.audio_data.len() * 2);
            for sample in &self.audio_data
            {
                stereo_data.push(*sample);
                stereo_data.push(*sample);
            }
            self.audio_data = stereo_data;
            self.channels = 2;
        }

        Ok(())
    }

    fn append_audio_buffer(&mut self, audio_buf: AudioBufferRef)
    {
        match audio_buf
        {
            AudioBufferRef::F32(buf) =>
            {
                for frame in 0..buf.frames()
                {
                    for ch in 0..buf.spec().channels.count()
                    {
                        self.audio_data.push(buf.chan(ch)[frame]);
                    }
                }
            }
            AudioBufferRef::S32(buf) =>
            {
                for frame in 0..buf.frames()
                {
                    for ch in 0..buf.spec().channels.count()
                    {
                        self.audio_data.push(buf.chan(ch)[frame] as f32 / i32::MAX as f32);
                    }
                }
            }
            AudioBufferRef::S16(buf) =>
            {
                for frame in 0..buf.frames()
                {
                    for ch in 0..buf.spec().channels.count()
                    {
                        self.audio_data.push(buf.chan(ch)[frame] as f32 / i16::MAX as f32);
                    }
                }
            }
            _ => {}
        }
    }

    pub fn get_waveform_data(&self, samples_per_pixel: usize) -> Vec<(f32, f32)>
    {
        if self.audio_data.is_empty()
        {
            return Vec::new();
        }

        let frame_count = self.audio_data.len() / self.channels;
        let pixel_count = (frame_count + samples_per_pixel - 1) / samples_per_pixel;
        let mut waveform = Vec::with_capacity(pixel_count);

        for i in 0..pixel_count
        {
            let start = i * samples_per_pixel * self.channels;
            let end = ((i + 1) * samples_per_pixel * self.channels).min(self.audio_data.len());

            let mut min = 0.0f32;
            let mut max = 0.0f32;

            for j in (start..end).step_by(self.channels)
            {
                // Average the channels for display
                let mut sample = 0.0;
                for ch in 0..self.channels.min(2)
                {
                    if j + ch < self.audio_data.len()
                    {
                        sample += self.audio_data[j + ch];
                    }
                }
                sample /= self.channels.min(2) as f32;

                min = min.min(sample);
                max = max.max(sample);
            }

            waveform.push((min, max));
        }

        waveform
    }

    pub fn get_sample_rate(&self) -> u32
    {
        self.sample_rate
    }

    pub fn get_duration(&self) -> f64
    {
        if self.audio_data.is_empty()
        {
            return 0.0;
        }
        (self.audio_data.len() / self.channels) as f64 / self.sample_rate as f64
    }

    pub fn play(&mut self, start_time: Option<f64>, end_time: Option<f64>) -> Result<(), String>
    {
        // Check if we have a paused playback to resume
        if let Some(ref mut playback) = self.playback
        {
            if playback.is_paused()
            {
                playback.resume()?;
                return Ok(());
            }
        }

        let start_frame = start_time.map(|t| (t * self.sample_rate as f64) as usize).unwrap_or(0);
        let end_frame = end_time
            .map(|t| (t * self.sample_rate as f64) as usize)
            .unwrap_or(self.audio_data.len() / self.channels);

        let start_sample = start_frame * self.channels;
        let end_sample = end_frame * self.channels;

        let audio_slice = &self.audio_data[start_sample.min(self.audio_data.len())..end_sample.min(self.audio_data.len())];

        if self.playback.is_none()
        {
            self.playback = Some(AudioPlayback::new(self.sample_rate, self.channels)?);
        }

        if let Some(ref mut playback) = self.playback
        {
            playback.play(audio_slice.to_vec(), start_frame as f64 / self.sample_rate as f64)?;
        }

        Ok(())
    }

    pub fn pause(&mut self)
    {
        if let Some(ref mut playback) = self.playback
        {
            playback.pause();
        }
    }

    pub fn stop(&mut self)
    {
        if let Some(ref mut playback) = self.playback
        {
            playback.stop();
        }
    }

    pub fn is_playing(&self) -> bool
    {
        self.playback.as_ref().map(|p| p.is_playing()).unwrap_or(false)
    }

    pub fn get_playback_position(&self) -> f64
    {
        self.playback
            .as_ref()
            .map(|p| p.get_position())
            .unwrap_or(0.0)
    }

    pub fn set_playback_position(&mut self, position: f64)
    {
        if let Some(ref mut playback) = self.playback
        {
            playback.set_position(position);
        }
    }

    pub fn delete_region(&mut self, start_time: f64, end_time: f64) -> Result<(), String>
    {
        let start_frame = (start_time * self.sample_rate as f64) as usize;
        let end_frame = (end_time * self.sample_rate as f64) as usize;

        let start_sample = start_frame * self.channels;
        let end_sample = end_frame * self.channels;

        if start_sample >= self.audio_data.len()
        {
            return Err("Start position out of bounds".to_string());
        }

        let end_sample = end_sample.min(self.audio_data.len());
        self.audio_data.drain(start_sample..end_sample);

        Ok(())
    }

    pub fn export_audio(&self, path: &str, start_time: Option<f64>, end_time: Option<f64>,
                       compression_level: Option<u8>, bitrate_kbps: Option<u32>) -> Result<(), String>
    {
        let start_frame = start_time.map(|t| (t * self.sample_rate as f64) as usize).unwrap_or(0);
        let end_frame = end_time
            .map(|t| (t * self.sample_rate as f64) as usize)
            .unwrap_or(self.audio_data.len() / self.channels);

        let start_sample = start_frame * self.channels;
        let end_sample = (end_frame * self.channels).min(self.audio_data.len());

        let export_data = &self.audio_data[start_sample..end_sample];

        let path_lower = path.to_lowercase();
        if path_lower.ends_with(".wav")
        {
            self.export_wav(path, export_data)?;
        }
        else if path_lower.ends_with(".flac")
        {
            self.export_flac(path, export_data, compression_level.unwrap_or(5))?;
        }
        else if path_lower.ends_with(".mp3")
        {
            self.export_mp3(path, export_data, bitrate_kbps.unwrap_or(192))?;
        }
        else
        {
            return Err("Unsupported format. Use .wav, .flac, or .mp3".to_string());
        }

        Ok(())
    }

    fn export_wav(&self, path: &str, data: &[f32]) -> Result<(), String>
    {
        let spec = hound::WavSpec {
            channels: self.channels as u16,
            sample_rate: self.sample_rate,
            bits_per_sample: 16,
            sample_format: hound::SampleFormat::Int,
        };

        let mut writer = hound::WavWriter::create(path, spec)
            .map_err(|e| format!("Failed to create WAV file: {}", e))?;

        for &sample in data
        {
            let sample_i16 = (sample.clamp(-1.0, 1.0) * i16::MAX as f32) as i16;
            writer.write_sample(sample_i16)
                .map_err(|e| format!("Failed to write sample: {}", e))?;
        }

        writer.finalize()
            .map_err(|e| format!("Failed to finalize WAV: {}", e))?;

        Ok(())
    }

    fn export_flac(&self, path: &str, data: &[f32], compression_level: u8) -> Result<(), String>
    {
        use flacenc::{encode_with_fixed_block_size, config};
        use flacenc::source::MemSource;
        use flacenc::error::Verify;
        use flacenc::component::BitRepr;
        use flacenc::bitsink::MemSink;

        // Convert f32 to i32 for FLAC encoding
        let mut samples_i32 = Vec::with_capacity(data.len());

        for &sample in data
        {
            let sample_i32 = (sample.clamp(-1.0, 1.0) * ((1i32 << 23) - 1) as f32) as i32;
            samples_i32.push(sample_i32);
        }

        // Create the encoder config
        // The flacenc crate uses preset configurations based on compression levels
        let config = match compression_level
        {
            0 => config::Encoder::preset_0(),  // Fastest
            1 => config::Encoder::preset_1(),
            2 => config::Encoder::preset_2(),
            3 => config::Encoder::preset_3(),
            4 => config::Encoder::preset_4(),
            5 => config::Encoder::preset_5(),  // Default
            6 => config::Encoder::preset_6(),
            7 => config::Encoder::preset_7(),
            8 => config::Encoder::preset_8(),  // Best compression
            _ => config::Encoder::preset_5(),  // Default for invalid values
        };

        let config = config.into_verified()
            .map_err(|e| format!("Failed to verify config: {:?}", e))?;

        // Create memory source
        let source = MemSource::from_samples(
            &samples_i32,
            self.channels,
            24,
            self.sample_rate as usize,
        );

        // Encode to FLAC
        let stream = encode_with_fixed_block_size(
            &config,
            source,
            4096,
        ).map_err(|e| format!("FLAC encoding error: {:?}", e))?;

        // Convert stream to bytes using MemSink
        let bitcount = stream.count_bits();
        let mut sink = MemSink::with_capacity(bitcount);
        stream.write(&mut sink)
            .map_err(|e| format!("Failed to write FLAC stream: {:?}", e))?;
        let output = sink.into_inner();

        // Write to file
        let mut file = File::create(path)
            .map_err(|e| format!("Failed to create FLAC file: {}", e))?;

        file.write_all(&output)
            .map_err(|e| format!("Failed to write FLAC file: {}", e))?;

        Ok(())
    }

    fn export_mp3(&self, path: &str, data: &[f32], bitrate_kbps: u32) -> Result<(), String>
    {
        use mp3lame_encoder::{Builder, InterleavedPcm, FlushNoGap, Bitrate};
        use std::mem::MaybeUninit;

        // Convert to stereo interleaved i16 samples
        let mut samples_i16 = Vec::with_capacity(data.len());
        for &sample in data
        {
            let sample_i16 = (sample.clamp(-1.0, 1.0) * i16::MAX as f32) as i16;
            samples_i16.push(sample_i16);
        }

        // Setup MP3 encoder
        let mut mp3_encoder = Builder::new()
            .ok_or("Failed to create MP3 encoder")?;

        mp3_encoder.set_sample_rate(self.sample_rate)
            .map_err(|e| format!("Failed to set sample rate: {:?}", e))?;

        mp3_encoder.set_num_channels(self.channels as u8)
            .map_err(|e| format!("Failed to set channels: {:?}", e))?;

        // Set bitrate based on parameter
        let bitrate = match bitrate_kbps
        {
            128 => Bitrate::Kbps128,
            160 => Bitrate::Kbps160,
            192 => Bitrate::Kbps192,
            256 => Bitrate::Kbps256,
            320 => Bitrate::Kbps320,
            _ => Bitrate::Kbps192,  // Default to 192
        };

        mp3_encoder.set_brate(bitrate)
            .map_err(|e| format!("Failed to set bitrate: {:?}", e))?;

        mp3_encoder.set_quality(mp3lame_encoder::Quality::Good)
            .map_err(|e| format!("Failed to set quality: {:?}", e))?;

        let mut mp3_encoder = mp3_encoder.build()
            .map_err(|e| format!("Failed to build encoder: {:?}", e))?;

        // Encode
        let input = InterleavedPcm(&samples_i16);
        let mut mp3_out = Vec::new();

        // Calculate proper buffer size: 1.25 * num_samples + 7200
        // This is the formula recommended by LAME for worst-case output size
        let buffer_size = (samples_i16.len() * 5 / 4 + 7200).max(16384);
        let mut output: Vec<MaybeUninit<u8>> = vec![MaybeUninit::uninit(); buffer_size];

        let encoded_size = mp3_encoder.encode(input, &mut output[..])
            .map_err(|e| format!("Failed to encode MP3: {:?}", e))?;

        // Safely convert MaybeUninit to initialized bytes
        for i in 0..encoded_size
        {
            unsafe {
                mp3_out.push(output[i].assume_init());
            }
        }

        // Flush remaining data - specify FlushNoGap type parameter
        let _flushed_size = mp3_encoder.flush_to_vec::<FlushNoGap>(&mut mp3_out)
            .map_err(|e| format!("Failed to flush MP3: {:?}", e))?;

        // Write to file
        let mut file = File::create(path)
            .map_err(|e| format!("Failed to create MP3 file: {}", e))?;
        file.write_all(&mp3_out)
            .map_err(|e| format!("Failed to write MP3 file: {}", e))?;

        Ok(())
    }
}