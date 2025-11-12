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
        AudioEngine
        {
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

        if self.channels == 2
        {
            // Return stereo waveform data (min_L, max_L, min_R, max_R)
            // We'll encode it as two tuples per pixel for Python
            for i in 0..pixel_count
            {
                let start = i * samples_per_pixel;
                let end = ((i + 1) * samples_per_pixel).min(frame_count);

                let mut min_l = 0.0f32;
                let mut max_l = 0.0f32;
                let mut min_r = 0.0f32;
                let mut max_r = 0.0f32;

                for j in start..end
                {
                    let idx = j * 2;
                    if idx + 1 < self.audio_data.len()
                    {
                        let left = self.audio_data[idx];
                        let right = self.audio_data[idx + 1];

                        min_l = min_l.min(left);
                        max_l = max_l.max(left);
                        min_r = min_r.min(right);
                        max_r = max_r.max(right);
                    }
                }

                // For stereo, we'll return a tuple of 4 values encoded as 2 tuples
                // Python will check the length to determine if it's stereo
                waveform.push((min_l, max_l));
                waveform.push((min_r, max_r));
            }

            // Actually, let's use a different approach - return proper stereo data
            // Clear and rebuild with proper format
            waveform.clear();
            for i in 0..pixel_count
            {
                let start = i * samples_per_pixel;
                let end = ((i + 1) * samples_per_pixel).min(frame_count);

                let mut min_l = 0.0f32;
                let mut max_l = 0.0f32;
                let mut min_r = 0.0f32;
                let mut max_r = 0.0f32;

                for j in start..end
                {
                    let idx = j * 2;
                    if idx + 1 < self.audio_data.len()
                    {
                        let left = self.audio_data[idx];
                        let right = self.audio_data[idx + 1];

                        min_l = min_l.min(left);
                        max_l = max_l.max(left);
                        min_r = min_r.min(right);
                        max_r = max_r.max(right);
                    }
                }

                // Use average for now (will fix Python to handle stereo properly)
                let min_avg = (min_l + min_r) / 2.0;
                let max_avg = (max_l + max_r) / 2.0;
                waveform.push((min_avg, max_avg));
            }
        }
        else
        {
            // Mono or averaged display
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
                    for ch in 0..self.channels
                    {
                        if j + ch < self.audio_data.len()
                        {
                            sample += self.audio_data[j + ch];
                        }
                    }
                    sample /= self.channels as f32;

                    min = min.min(sample);
                    max = max.max(sample);
                }

                waveform.push((min, max));
            }
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

    pub fn get_channels(&self) -> usize
    {
        self.channels
    }

    pub fn get_stereo_waveform_data(&self, samples_per_pixel: usize) -> Vec<(f32, f32, f32, f32)>
    {
        if self.audio_data.is_empty()
        {
            return Vec::new();
        }

        let frame_count = self.audio_data.len() / self.channels;
        let pixel_count = (frame_count + samples_per_pixel - 1) / samples_per_pixel;
        let mut waveform = Vec::with_capacity(pixel_count);

        if self.channels == 2
        {
            // Return stereo waveform data (min_L, max_L, min_R, max_R)
            for i in 0..pixel_count
            {
                let start = i * samples_per_pixel;
                let end = ((i + 1) * samples_per_pixel).min(frame_count);

                let mut min_l = 0.0f32;
                let mut max_l = 0.0f32;
                let mut min_r = 0.0f32;
                let mut max_r = 0.0f32;

                for j in start..end
                {
                    let idx = j * 2;
                    if idx + 1 < self.audio_data.len()
                    {
                        let left = self.audio_data[idx];
                        let right = self.audio_data[idx + 1];

                        min_l = min_l.min(left);
                        max_l = max_l.max(left);
                        min_r = min_r.min(right);
                        max_r = max_r.max(right);
                    }
                }

                waveform.push((min_l, max_l, min_r, max_r));
            }
        }
        else
        {
            // For mono, duplicate the channel
            for i in 0..pixel_count
            {
                let start = i * samples_per_pixel * self.channels;
                let end = ((i + 1) * samples_per_pixel * self.channels).min(self.audio_data.len());

                let mut min = 0.0f32;
                let mut max = 0.0f32;

                for j in (start..end).step_by(self.channels)
                {
                    if j < self.audio_data.len()
                    {
                        let sample = self.audio_data[j];
                        min = min.min(sample);
                        max = max.max(sample);
                    }
                }

                waveform.push((min, max, min, max));
            }
        }

        waveform
    }

    pub fn get_waveform_for_range(&self, start_time: f64, end_time: f64, num_pixels: usize) -> Vec<(f32, f32, f32, f32)>
    {
        if self.audio_data.is_empty() || num_pixels == 0
        {
            return Vec::new();
        }

        let start_frame = ((start_time * self.sample_rate as f64) as usize).min(self.audio_data.len() / self.channels);
        let end_frame = ((end_time * self.sample_rate as f64) as usize).min(self.audio_data.len() / self.channels);

        if start_frame >= end_frame
        {
            return Vec::new();
        }

        let frame_count = end_frame - start_frame;
        let samples_per_pixel = (frame_count as f64) / (num_pixels as f64);

        // When zoomed in enough to see individual samples (< 1 sample per pixel),
        // return one data point per sample instead of one per pixel
        if samples_per_pixel < 1.0
        {
            // Return individual samples
            let mut waveform = Vec::with_capacity(frame_count);

            for frame in start_frame..end_frame
            {
                if self.channels == 2
                {
                    let idx = frame * 2;
                    if idx + 1 < self.audio_data.len()
                    {
                        let left = self.audio_data[idx];
                        let right = self.audio_data[idx + 1];
                        // For individual samples, min and max are the same value
                        waveform.push((left, left, right, right));
                    }
                }
                else
                {
                    let idx = frame * self.channels;
                    if idx < self.audio_data.len()
                    {
                        let sample = self.audio_data[idx];
                        // For mono, duplicate the values
                        waveform.push((sample, sample, sample, sample));
                    }
                }
            }

            return waveform;
        }

        // Normal case: downsample to one data point per pixel
        let mut waveform = Vec::with_capacity(num_pixels);

        for i in 0..num_pixels
        {
            let pixel_start_frame = start_frame + (i as f64 * samples_per_pixel) as usize;
            let pixel_end_frame = (start_frame + ((i + 1) as f64 * samples_per_pixel) as usize).min(end_frame);

            if pixel_start_frame >= pixel_end_frame
            {
                waveform.push((0.0, 0.0, 0.0, 0.0));
                continue;
            }

            if self.channels == 2
            {
                // Stereo - separate left and right channels
                let mut min_l = 0.0f32;
                let mut max_l = 0.0f32;
                let mut min_r = 0.0f32;
                let mut max_r = 0.0f32;

                for frame in pixel_start_frame..pixel_end_frame
                {
                    let idx = frame * 2;
                    if idx + 1 < self.audio_data.len()
                    {
                        let left = self.audio_data[idx];
                        let right = self.audio_data[idx + 1];

                        min_l = min_l.min(left);
                        max_l = max_l.max(left);
                        min_r = min_r.min(right);
                        max_r = max_r.max(right);
                    }
                }

                waveform.push((min_l, max_l, min_r, max_r));
            }
            else
            {
                // Mono - single channel
                let mut min_val = 0.0f32;
                let mut max_val = 0.0f32;

                for frame in pixel_start_frame..pixel_end_frame
                {
                    let idx = frame * self.channels;
                    if idx < self.audio_data.len()
                    {
                        let sample = self.audio_data[idx];
                        min_val = min_val.min(sample);
                        max_val = max_val.max(sample);
                    }
                }

                // For mono, duplicate the values to maintain consistent tuple size
                waveform.push((min_val, max_val, min_val, max_val));
            }
        }

        waveform
    }

    pub fn play(&mut self, start_time: Option<f64>, end_time: Option<f64>) -> Result<(), String>
    {
        // If both start and end are None and we have paused playback, resume
        if start_time.is_none() && end_time.is_none()
        {
            if let Some(ref mut playback) = self.playback
            {
                if playback.is_paused()
                {
                    playback.resume()?;
                    return Ok(());
                }
            }
        }

        // Otherwise start new playback
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
        let spec = hound::WavSpec
        {
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
        use std::path::Path;

        // Use the custom FLAC encoder
        crate::flac::export_to_flac_with_level(
            Path::new(path),
            data,
            self.sample_rate,
            self.channels as u16,
            compression_level,
        )
            .map_err(|e| format!("Failed to export FLAC: {}", e))?;

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
        let buffer_size = (samples_i16.len() * 5 / 4 + 7200).max(16384);
        let mut output: Vec<MaybeUninit<u8>> = vec![MaybeUninit::uninit(); buffer_size];

        let encoded_size = mp3_encoder.encode(input, &mut output[..])
                                      .map_err(|e| format!("Failed to encode MP3: {:?}", e))?;

        // Safely convert MaybeUninit to initialized bytes
        for i in 0..encoded_size
        {
            unsafe
                {
                    mp3_out.push(output[i].assume_init());
                }
        }

        // Flush remaining data
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