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

/// Represents a single audio track
pub struct AudioTrack
{
    pub audio_data: Vec<f32>,
    pub sample_rate: u32,
    pub channels: usize,
    pub name: String,
}

/// Core audio engine for loading, processing, and exporting audio
pub struct AudioEngine
{
    tracks: Vec<AudioTrack>,
    playback: Option<AudioPlayback>,
    playback_sample_rate: Option<u32>,
}

impl AudioEngine
{
    /// Create a new audio engine instance
    ///
    /// # Returns
    /// `AudioEngine` - new engine with no tracks loaded
    pub fn new() -> Self
    {
        AudioEngine
        {
            tracks: Vec::new(),
            playback: None,
            playback_sample_rate: None,
        }
    }

    /// Load and decode an audio file as a new track
    ///
    /// # Parameters
    /// * `path` - filesystem path to audio file
    ///
    /// # Returns
    /// `Result<(u32, usize, Option<u32>), String>` - Ok with (sample_rate, channels, mismatched_rate) if successful
    ///
    /// # Notes
    /// Preserves original channel configuration (mono or stereo).
    /// Returns the previous sample rate if there's a mismatch with existing tracks.
    pub fn load_file(&mut self, path: &str) -> Result<(u32, usize, Option<u32>), String>
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

        let sample_rate = track.codec_params.sample_rate.unwrap_or(44100);
        let channels = track.codec_params.channels.unwrap_or_default().count();
        let mut audio_data = Vec::new();

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
                    Self::append_audio_buffer(&mut audio_data, audio_buf, channels);
                }
                Err(_) => continue,
            }
        }

        let track_name = Path::new(path)
            .file_name()
            .and_then(|n| n.to_str())
            .unwrap_or("Unknown")
            .to_string();

        let mismatched_rate = if !self.tracks.is_empty()
        {
            let existing_rate = self.tracks[0].sample_rate;
            if existing_rate != sample_rate
            {
                Some(existing_rate)
            }
            else
            {
                None
            }
        }
        else
        {
            None
        };

        let new_track = AudioTrack
        {
            audio_data,
            sample_rate,
            channels,
            name: track_name,
        };

        self.tracks.push(new_track);

        Ok((sample_rate, channels, mismatched_rate))
    }

    /// Append decoded audio buffer to storage
    ///
    /// # Parameters
    /// * `audio_data` - vector to append to
    /// * `audio_buf` - decoded audio buffer from symphonia
    /// * `channels` - number of channels
    ///
    /// # Notes
    /// Handles F32, S32, and S16 sample formats, converting to F32
    fn append_audio_buffer(audio_data: &mut Vec<f32>, audio_buf: AudioBufferRef, channels: usize)
    {
        match audio_buf
        {
            AudioBufferRef::F32(buf) =>
            {
                // pass through f32 samples as is
                for frame in 0..buf.frames()
                {
                    for ch in 0..channels.min(buf.spec().channels.count())
                    {
                        audio_data.push(buf.chan(ch)[frame]);
                    }
                }
            }
            AudioBufferRef::S32(buf) =>
            {
                // convert signed 32-bit integer samples to f32
                for frame in 0..buf.frames()
                {
                    for ch in 0..channels.min(buf.spec().channels.count())
                    {
                        audio_data.push(buf.chan(ch)[frame] as f32 / i32::MAX as f32);
                    }
                }
            }
            AudioBufferRef::S16(buf) =>
            {
                // convert signed 16-bit integer samples to f32
                for frame in 0..buf.frames()
                {
                    for ch in 0..channels.min(buf.spec().channels.count())
                    {
                        audio_data.push(buf.chan(ch)[frame] as f32 / i16::MAX as f32);
                    }
                }
            }
            _ => {}
        }
    }

    /// Get sample rate of the first loaded track
    ///
    /// # Returns
    /// `u32` - sample rate in Hz, or 44100 if no tracks loaded
    pub fn get_sample_rate(&self) -> u32
    {
        self.tracks.first().map(|t| t.sample_rate).unwrap_or(44100)
    }

    /// Get duration of the longest track
    ///
    /// # Returns
    /// `f64` - duration in seconds
    pub fn get_duration(&self) -> f64
    {
        self.tracks.iter().map(|track|
        {
            if track.audio_data.is_empty()
            {
                0.0
            }
            else
            {
                (track.audio_data.len() / track.channels) as f64 / track.sample_rate as f64
            }
        }).fold(0.0, f64::max)
    }

    /// Get number of audio channels (maximum across all tracks)
    ///
    /// # Returns
    /// `usize` - number of channels
    pub fn get_channels(&self) -> usize
    {
        self.tracks.iter().map(|t| t.channels).max().unwrap_or(2)
    }

    /// Get number of loaded tracks
    ///
    /// # Returns
    /// `usize` - number of tracks
    pub fn get_track_count(&self) -> usize
    {
        self.tracks.len()
    }

    /// Get information about all loaded tracks
    ///
    /// # Returns
    /// `Vec<(String, u32, usize, f64)>` - vector of (name, sample_rate, channels, duration)
    pub fn get_track_info(&self) -> Vec<(String, u32, usize, f64)>
    {
        self.tracks.iter().map(|track|
        {
            let duration = if track.audio_data.is_empty()
            {
                0.0
            }
            else
            {
                (track.audio_data.len() / track.channels) as f64 / track.sample_rate as f64
            };
            (track.name.clone(), track.sample_rate, track.channels, duration)
        }).collect()
    }

    /// Clear all loaded tracks
    pub fn clear_tracks(&mut self)
    {
        self.tracks.clear();
        self.playback = None;
        self.playback_sample_rate = None;
    }

    /// Get waveform data for a specific time range for all tracks
    ///
    /// # Parameters
    /// * `start_time` - start of range in seconds
    /// * `end_time` - end of range in seconds
    /// * `num_pixels` - desired number of display pixels
    ///
    /// # Returns
    /// `Vec<Vec<(f32, f32, f32, f32)>>` - waveform data per track as (min_l, max_l, min_r, max_r) tuples
    ///
    /// # Notes
    /// Returns separate waveform data for each track. For mono audio, left and right
    /// values are identical.
    pub fn get_waveform_for_range(&self, start_time: f64, end_time: f64, num_pixels: usize) -> Vec<Vec<(f32, f32, f32, f32)>>
    {
        if self.tracks.is_empty() || num_pixels == 0
        {
            return Vec::new();
        }

        self.tracks.iter().map(|track|
        {
            Self::get_track_waveform(track, start_time, end_time, num_pixels)
        }).collect()
    }

    /// Get waveform data for a single track
    ///
    /// # Parameters
    /// * `track` - audio track to analyze
    /// * `start_time` - start of range in seconds
    /// * `end_time` - end of range in seconds
    /// * `num_pixels` - desired number of display pixels
    ///
    /// # Returns
    /// `Vec<(f32, f32, f32, f32)>` - waveform data as (min_l, max_l, min_r, max_r) tuples
    fn get_track_waveform(track: &AudioTrack, start_time: f64, end_time: f64, num_pixels: usize) -> Vec<(f32, f32, f32, f32)>
    {
        if track.audio_data.is_empty() || num_pixels == 0
        {
            return vec![(0.0, 0.0, 0.0, 0.0); num_pixels];
        }

        let start_frame = ((start_time * track.sample_rate as f64) as usize).min(track.audio_data.len() / track.channels);
        let end_frame = ((end_time * track.sample_rate as f64) as usize).min(track.audio_data.len() / track.channels);

        if start_frame >= end_frame
        {
            return vec![(0.0, 0.0, 0.0, 0.0); num_pixels];
        }

        let frame_count = end_frame - start_frame;
        let samples_per_pixel = (frame_count as f64) / (num_pixels as f64);

        if samples_per_pixel < 1.0
        {
            // we're zoomed in far enough to see individual samples
            // return one entry per actual sample (not per pixel) so Python
            // can draw discrete bars with gaps between them
            let mut waveform = Vec::with_capacity(frame_count);

            for frame in start_frame..end_frame
            {
                if track.channels == 2
                {
                    let idx = frame * 2;
                    if idx + 1 < track.audio_data.len()
                    {
                        let left = track.audio_data[idx];
                        let right = track.audio_data[idx + 1];
                        // return (0, sample) so bars are drawn from center to value
                        waveform.push((0.0, left, 0.0, right));
                    }
                    else
                    {
                        waveform.push((0.0, 0.0, 0.0, 0.0));
                    }
                }
                else if track.channels == 1
                {
                    if frame < track.audio_data.len()
                    {
                        let sample = track.audio_data[frame];
                        // return (0, sample) so bars are drawn from center to value
                        waveform.push((0.0, sample, 0.0, sample));
                    }
                    else
                    {
                        waveform.push((0.0, 0.0, 0.0, 0.0));
                    }
                }
                else
                {
                    let idx = frame * track.channels;
                    if idx < track.audio_data.len()
                    {
                        let sample = track.audio_data[idx];
                        // return (0, sample) so bars are drawn from center to value
                        waveform.push((0.0, sample, 0.0, sample));
                    }
                    else
                    {
                        waveform.push((0.0, 0.0, 0.0, 0.0));
                    }
                }
            }

            // early return to bypass max/min rendering
            return waveform;
        }

        let mut waveform = Vec::with_capacity(num_pixels);

        for i in 0..num_pixels
        {
            // normal case: display max/min for the range covered by each pixel
            let pixel_start_frame = start_frame + (i as f64 * samples_per_pixel) as usize;
            let pixel_end_frame = (start_frame + ((i + 1) as f64 * samples_per_pixel) as usize).min(end_frame);

            if pixel_start_frame >= pixel_end_frame
            {
                waveform.push((0.0, 0.0, 0.0, 0.0));
                continue;
            }

            if track.channels == 2
            {
                let mut min_l = 0.0f32;
                let mut max_l = 0.0f32;
                let mut min_r = 0.0f32;
                let mut max_r = 0.0f32;

                for frame in pixel_start_frame..pixel_end_frame
                {
                    let idx = frame * 2;
                    if idx + 1 < track.audio_data.len()
                    {
                        let left = track.audio_data[idx];
                        let right = track.audio_data[idx + 1];

                        min_l = min_l.min(left);
                        max_l = max_l.max(left);
                        min_r = min_r.min(right);
                        max_r = max_r.max(right);
                    }
                }

                waveform.push((min_l, max_l, min_r, max_r));
            }
            else if track.channels == 1
            {
                let mut min_val = 0.0f32;
                let mut max_val = 0.0f32;

                for frame in pixel_start_frame..pixel_end_frame
                {
                    if frame < track.audio_data.len()
                    {
                        let sample = track.audio_data[frame];
                        min_val = min_val.min(sample);
                        max_val = max_val.max(sample);
                    }
                }

                waveform.push((min_val, max_val, min_val, max_val));
            }
            else
            {
                let mut min_val = 0.0f32;
                let mut max_val = 0.0f32;

                for frame in pixel_start_frame..pixel_end_frame
                {
                    let idx = frame * track.channels;
                    if idx < track.audio_data.len()
                    {
                        let sample = track.audio_data[idx];
                        min_val = min_val.min(sample);
                        max_val = max_val.max(sample);
                    }
                }

                waveform.push((min_val, max_val, min_val, max_val));
            }
        }

        waveform
    }

    /// Mix all tracks together for playback
    ///
    /// # Parameters
    /// * `start_time` - start time in seconds
    /// * `end_time` - end time in seconds
    ///
    /// # Returns
    /// `(Vec<f32>, u32, usize)` - mixed audio data, sample rate, and channel count
    ///
    /// # Notes
    /// Preserves mono if all tracks are mono, otherwise converts to stereo.
    /// Uses the sample rate of the first track.
    fn mix_tracks_for_playback(&self, start_time: f64, end_time: f64) -> (Vec<f32>, u32, usize)
    {
        if self.tracks.is_empty()
        {
            return (Vec::new(), 44100, 2);
        }

        let sample_rate = self.tracks[0].sample_rate;
        let has_stereo = self.tracks.iter().any(|t| t.channels == 2);
        let output_channels = if has_stereo { 2 } else { 1 };

        let start_frame = (start_time * sample_rate as f64) as usize;
        let end_frame = (end_time * sample_rate as f64) as usize;
        let total_frames = end_frame.saturating_sub(start_frame);

        if total_frames == 0
        {
            return (Vec::new(), sample_rate, output_channels);
        }

        let mut mixed_data = vec![0.0f32; total_frames * output_channels];

        for track in &self.tracks
        {
            // calculate frame range in this track's sample rate
            let track_start_frame = (start_time * track.sample_rate as f64) as usize;
            let track_end_frame = (end_time * track.sample_rate as f64) as usize;
            let track_total_frames = track_end_frame.saturating_sub(track_start_frame);

            for frame_idx in 0..total_frames.min(track_total_frames)
            {
                let track_frame = track_start_frame + frame_idx;
                let output_idx = frame_idx * output_channels;

                // skip if track has ended
                if track_frame >= track.audio_data.len() / track.channels
                {
                    break;
                }

                if output_channels == 2
                {
                    if track.channels == 2
                    {
                        let track_idx = track_frame * 2;
                        if track_idx + 1 < track.audio_data.len()
                        {
                            mixed_data[output_idx] += track.audio_data[track_idx];
                            mixed_data[output_idx + 1] += track.audio_data[track_idx + 1];
                        }
                    }
                    else if track.channels == 1
                    {
                        if track_frame < track.audio_data.len()
                        {
                            let sample = track.audio_data[track_frame];
                            mixed_data[output_idx] += sample;
                            mixed_data[output_idx + 1] += sample;
                        }
                    }
                }
                else
                {
                    if track.channels == 1
                    {
                        if track_frame < track.audio_data.len()
                        {
                            mixed_data[output_idx] += track.audio_data[track_frame];
                        }
                    }
                }
            }
        }

        for sample in &mut mixed_data
        {
            *sample = sample.clamp(-1.0, 1.0);
        }

        (mixed_data, sample_rate, output_channels)
    }

    /// Mix tracks with specific channel mode for export
    ///
    /// # Parameters
    /// * `start_time` - start time in seconds
    /// * `end_time` - end time in seconds
    /// * `channel_mode` - channel configuration mode
    ///
    /// # Returns
    /// `Vec<(Vec<f32>, u32, usize, String)>` - list of (audio data, sample rate, channels, suffix)
    ///
    /// # Notes
    /// Returns multiple results for split mode, single result otherwise
    fn mix_tracks_for_export(&self, start_time: f64, end_time: f64, channel_mode: &str) -> Vec<(Vec<f32>, u32, usize, String)>
    {
        if self.tracks.is_empty()
        {
            return vec![(Vec::new(), 44100, 2, String::new())];
        }

        let sample_rate = self.tracks[0].sample_rate;
        let start_frame = (start_time * sample_rate as f64) as usize;
        let end_frame = (end_time * sample_rate as f64) as usize;
        let total_frames = end_frame.saturating_sub(start_frame);

        if total_frames == 0
        {
            return vec![(Vec::new(), sample_rate, 2, String::new())];
        }

        match channel_mode
        {
            "split" =>
            {
                // split all stereo tracks to separate mono tracks with _L and _R suffixes
                let mut results = Vec::new();
                for track in &self.tracks
                {
                    if track.channels == 2
                    {
                        let track_start_frame = (start_time * track.sample_rate as f64) as usize;
                        let track_total_frames = total_frames.min(
                            (track.audio_data.len() / 2).saturating_sub(track_start_frame)
                        );

                        let mut left_data = Vec::with_capacity(track_total_frames);
                        let mut right_data = Vec::with_capacity(track_total_frames);

                        for frame_idx in 0..track_total_frames
                        {
                            let track_frame = track_start_frame + frame_idx;
                            let track_idx = track_frame * 2;
                            if track_idx + 1 < track.audio_data.len()
                            {
                                left_data.push(track.audio_data[track_idx]);
                                right_data.push(track.audio_data[track_idx + 1]);
                            }
                            else
                            {
                                break;
                            }
                        }

                        results.push((left_data, sample_rate, 1, "_L".to_string()));
                        results.push((right_data, sample_rate, 1, "_R".to_string()));
                    }
                }
                if results.is_empty()
                {
                    results.push((Vec::new(), sample_rate, 1, String::new()));
                }
                results
            }
            "mono_to_stereo" =>
            {
                // combine pairs of mono tracks into stereo tracks
                let mut stereo_data = vec![0.0f32; total_frames * 2];

                let mono_tracks: Vec<&AudioTrack> = self.tracks.iter().filter(|t| t.channels == 1).collect();

                // process pairs of mono tracks
                for pair_idx in (0..mono_tracks.len()).step_by(2)
                {
                    if pair_idx + 1 >= mono_tracks.len()
                    {
                        break;
                    }

                    let left_track = mono_tracks[pair_idx];
                    let right_track = mono_tracks[pair_idx + 1];

                    let left_start = (start_time * left_track.sample_rate as f64) as usize;
                    let right_start = (start_time * right_track.sample_rate as f64) as usize;

                    for frame_idx in 0..total_frames
                    {
                        let output_idx = frame_idx * 2;

                        if left_start + frame_idx < left_track.audio_data.len()
                        {
                            stereo_data[output_idx] = left_track.audio_data[left_start + frame_idx];
                        }

                        if right_start + frame_idx < right_track.audio_data.len()
                        {
                            stereo_data[output_idx + 1] = right_track.audio_data[right_start + frame_idx];
                        }
                    }
                }

                vec![(stereo_data, sample_rate, 2, String::new())]
            }
            "mono" =>
            {
                // downmix all tracks to mono
                let mut mono_data = vec![0.0f32; total_frames];

                for track in &self.tracks
                {
                    let track_start_frame = (start_time * track.sample_rate as f64) as usize;
                    let track_total_frames = total_frames.min(
                        (track.audio_data.len() / track.channels).saturating_sub(track_start_frame)
                    );

                    for frame_idx in 0..track_total_frames
                    {
                        let track_frame = track_start_frame + frame_idx;

                        if track.channels == 2
                        {
                            let track_idx = track_frame * 2;
                            if track_idx + 1 < track.audio_data.len()
                            {
                                let mono_sample = (track.audio_data[track_idx] + track.audio_data[track_idx + 1]) / 2.0;
                                mono_data[frame_idx] += mono_sample;
                            }
                        }
                        else if track.channels == 1
                        {
                            if track_frame < track.audio_data.len()
                            {
                                mono_data[frame_idx] += track.audio_data[track_frame];
                            }
                        }
                    }
                }

                for sample in &mut mono_data
                {
                    *sample = sample.clamp(-1.0, 1.0);
                }

                vec![(mono_data, sample_rate, 1, String::new())]
            }
            _ =>
            {
                // default: mix all tracks however they would be played back
                let (data, rate, channels) = self.mix_tracks_for_playback(start_time, end_time);
                vec![(data, rate, channels, String::new())]
            }
        }
    }

    /// Start audio playback
    ///
    /// # Parameters
    /// * `start_time` - optional start time in seconds
    /// * `end_time` - optional end time in seconds
    ///
    /// # Returns
    /// `Result<(), String>` - Ok if successful
    ///
    /// # Notes
    /// If both times are None and playback is paused, resumes from current position.
    /// Mixes all tracks together for playback.
    pub fn play(&mut self, start_time: Option<f64>, end_time: Option<f64>) -> Result<(), String>
    {
        // resume paused playback if no times specified
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

        let duration = self.get_duration();
        let start = start_time.unwrap_or(0.0);
        let end = end_time.unwrap_or(duration);

        let (mixed_data, sample_rate, channels) = self.mix_tracks_for_playback(start, end);

        let needs_new_playback = self.playback.is_none() ||
            self.playback_sample_rate != Some(sample_rate);

        if needs_new_playback
        {
            self.playback = Some(AudioPlayback::new(sample_rate, channels)?);
            self.playback_sample_rate = Some(sample_rate);
        }

        if let Some(ref mut playback) = self.playback
        {
            playback.play(mixed_data, start)?;
        }

        Ok(())
    }

    /// Pause audio playback
    pub fn pause(&mut self)
    {
        if let Some(ref mut playback) = self.playback
        {
            playback.pause();
        }
    }

    /// Stop audio playback and reset position
    pub fn stop(&mut self)
    {
        if let Some(ref mut playback) = self.playback
        {
            playback.stop();
        }
    }

    /// Check if audio is currently playing
    ///
    /// # Returns
    /// `bool` - true if playing
    pub fn is_playing(&self) -> bool
    {
        self.playback.as_ref().map(|p| p.is_playing()).unwrap_or(false)
    }

    /// Get current playback position
    ///
    /// # Returns
    /// `f64` - position in seconds
    pub fn get_playback_position(&self) -> f64
    {
        self.playback
            .as_ref()
            .map(|p| p.get_position())
            .unwrap_or(0.0)
    }

    /// Set playback position
    ///
    /// # Parameters
    /// * `position` - new position in seconds
    pub fn set_playback_position(&mut self, position: f64)
    {
        if let Some(ref mut playback) = self.playback
        {
            playback.set_position(position);
        }
    }

    /// Delete a region of audio from specified tracks
    ///
    /// # Parameters
    /// * `start_time` - start of region in seconds
    /// * `end_time` - end of region in seconds
    /// * `track_indices` - slice of track indices to delete from
    ///
    /// # Returns
    /// `Result<(), String>` - Ok if successful
    pub fn delete_region(&mut self, start_time: f64, end_time: f64, track_indices: &[usize]) -> Result<(), String>
    {
        for &track_idx in track_indices
        {
            if track_idx >= self.tracks.len()
            {
                continue;
            }

            let track = &mut self.tracks[track_idx];
            let start_frame = (start_time * track.sample_rate as f64) as usize;
            let end_frame = (end_time * track.sample_rate as f64) as usize;

            let start_sample = start_frame * track.channels;
            let end_sample = end_frame * track.channels;

            if start_sample >= track.audio_data.len()
            {
                continue;
            }

            let end_sample = end_sample.min(track.audio_data.len());
            track.audio_data.drain(start_sample..end_sample);
        }

        Ok(())
    }

    /// Export audio to a file
    ///
    /// # Parameters
    /// * `path` - output file path with extension (.wav, .flac, or .mp3)
    /// * `start_time` - optional start time in seconds (None for beginning)
    /// * `end_time` - optional end time in seconds (None for end)
    /// * `compression_level` - optional FLAC compression level 0-8 (None for default 5)
    /// * `bitrate_kbps` - optional MP3 bitrate in kbps (None for default 192)
    /// * `channel_mode` - optional channel mode ('stereo', 'mono', 'split', 'mono_to_stereo')
    ///
    /// # Returns
    /// `Result<(), String>` - Ok if successful
    ///
    /// # Notes
    /// Format is determined by file extension. All tracks are mixed together for export.
    /// Split mode creates multiple files with _L and _R suffixes.
    pub fn export_audio(&self, path: &str, start_time: Option<f64>, end_time: Option<f64>,
                        compression_level: Option<u8>, bitrate_kbps: Option<u32>,
                        channel_mode: Option<String>) -> Result<(), String>
    {
        let duration = self.get_duration();
        let start = start_time.unwrap_or(0.0);
        let end = end_time.unwrap_or(duration);

        let mode = channel_mode.as_deref().unwrap_or("auto");
        let export_items = if mode == "auto"
        {
            let (data, rate, channels) = self.mix_tracks_for_playback(start, end);
            vec![(data, rate, channels, String::new())]
        }
        else
        {
            self.mix_tracks_for_export(start, end, mode)
        };

        let path_lower = path.to_lowercase();
        let (base_path, extension) = if let Some(pos) = path.rfind('.')
        {
            (&path[..pos], &path[pos..])
        }
        else
        {
            (path, "")
        };

        for (export_data, sample_rate, channels, suffix) in export_items
        {
            let final_path = if suffix.is_empty()
            {
                path.to_string()
            }
            else
            {
                format!("{}{}{}", base_path, suffix, extension)
            };

            if path_lower.ends_with(".wav")
            {
                self.export_wav(&final_path, &export_data, sample_rate, channels)?;
            }
            else if path_lower.ends_with(".flac")
            {
                self.export_flac(&final_path, &export_data, sample_rate, channels, compression_level.unwrap_or(5))?;
            }
            else if path_lower.ends_with(".mp3")
            {
                self.export_mp3(&final_path, &export_data, sample_rate, channels, bitrate_kbps.unwrap_or(192))?;
            }
            else
            {
                return Err("Unsupported format. Use .wav, .flac, or .mp3".to_string());
            }
        }

        Ok(())
    }

    /// Export audio as WAV file
    ///
    /// # Parameters
    /// * `path` - output file path
    /// * `data` - audio sample data
    /// * `sample_rate` - sample rate in Hz
    /// * `channels` - number of channels
    ///
    /// # Returns
    /// `Result<(), String>` - Ok if successful
    fn export_wav(&self, path: &str, data: &[f32], sample_rate: u32, channels: usize) -> Result<(), String>
    {
        let spec = hound::WavSpec
        {
            channels: channels as u16,
            sample_rate,
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

    /// Export audio as FLAC file
    ///
    /// # Parameters
    /// * `path` - output file path
    /// * `data` - audio sample data
    /// * `sample_rate` - sample rate in Hz
    /// * `channels` - number of channels
    /// * `compression_level` - compression level 0-8
    ///
    /// # Returns
    /// `Result<(), String>` - Ok if successful
    fn export_flac(&self, path: &str, data: &[f32], sample_rate: u32, channels: usize, compression_level: u8) -> Result<(), String>
    {
        use std::path::Path;

        crate::flac::export_to_flac_with_level(
            Path::new(path),
            data,
            sample_rate,
            channels as u16,
            compression_level,
        )
            .map_err(|e| format!("Failed to export FLAC: {}", e))?;

        Ok(())
    }

    /// Export audio as MP3 file
    ///
    /// # Parameters
    /// * `path` - output file path
    /// * `data` - audio sample data
    /// * `sample_rate` - sample rate in Hz
    /// * `channels` - number of channels
    /// * `bitrate_kbps` - bitrate in kbps (128, 160, 192, 256, or 320)
    ///
    /// # Returns
    /// `Result<(), String>` - Ok if successful
    fn export_mp3(&self, path: &str, data: &[f32], sample_rate: u32, channels: usize, bitrate_kbps: u32) -> Result<(), String>
    {
        use mp3lame_encoder::{Builder, InterleavedPcm, FlushNoGap, Bitrate};
        use std::mem::MaybeUninit;

        // convert to i16 samples
        let mut samples_i16 = Vec::with_capacity(data.len());
        for &sample in data
        {
            let sample_i16 = (sample.clamp(-1.0, 1.0) * i16::MAX as f32) as i16;
            samples_i16.push(sample_i16);
        }

        let mut mp3_encoder = Builder::new()
            .ok_or("Failed to create MP3 encoder")?;

        mp3_encoder.set_sample_rate(sample_rate)
                   .map_err(|e| format!("Failed to set sample rate: {:?}", e))?;

        mp3_encoder.set_num_channels(channels as u8)
                   .map_err(|e| format!("Failed to set channels: {:?}", e))?;

        let bitrate = match bitrate_kbps
        {
            128 => Bitrate::Kbps128,
            160 => Bitrate::Kbps160,
            192 => Bitrate::Kbps192,
            256 => Bitrate::Kbps256,
            320 => Bitrate::Kbps320,
            _ => Bitrate::Kbps192,
        };

        mp3_encoder.set_brate(bitrate)
                   .map_err(|e| format!("Failed to set bitrate: {:?}", e))?;

        mp3_encoder.set_quality(mp3lame_encoder::Quality::Good)
                   .map_err(|e| format!("Failed to set quality: {:?}", e))?;

        let mut mp3_encoder = mp3_encoder.build()
                                         .map_err(|e| format!("Failed to build encoder: {:?}", e))?;

        let input = InterleavedPcm(&samples_i16);
        let mut mp3_out = Vec::new();

        // calculate proper buffer size: 1.25 * num_samples + 7200
        let buffer_size = (samples_i16.len() * 5 / 4 + 7200).max(16384);
        let mut output: Vec<MaybeUninit<u8>> = vec![MaybeUninit::uninit(); buffer_size];

        let encoded_size = mp3_encoder.encode(input, &mut output[..])
                                      .map_err(|e| format!("Failed to encode MP3: {:?}", e))?;

        // safely convert MaybeUninit to initialized bytes
        for i in 0..encoded_size
        {
            unsafe
            {
                mp3_out.push(output[i].assume_init());
            }
        }

        let _flushed_size = mp3_encoder.flush_to_vec::<FlushNoGap>(&mut mp3_out)
                                       .map_err(|e| format!("Failed to flush MP3: {:?}", e))?;

        let mut file = File::create(path)
            .map_err(|e| format!("Failed to create MP3 file: {}", e))?;
        file.write_all(&mp3_out)
            .map_err(|e| format!("Failed to write MP3 file: {}", e))?;

        Ok(())
    }
}