//! Pure Rust FLAC encoder implementation based on RFC 9639
//! Currently supports all compression levels with 16-bit samples

use anyhow::{anyhow, Result};
use std::io::Write;
use std::path::Path;

/// FLAC file signature
const FLAC_SIGNATURE: [u8; 4] = [0x66, 0x4C, 0x61, 0x43]; // "fLaC"

/// Maximum Rice parameter value for 4-bit encoding
const MAX_RICE_PARAM_4BIT: u32 = 14;

/// Frame sync code
const FRAME_SYNC_CODE: u16 = 0x3FFE;

/// Build CRC-8 lookup table at runtime
///
/// # Returns
/// `[u8; 256]` - lookup table for CRC-8 calculation
///
/// # Notes
/// Uses FLAC polynomial (x^8 + x^2 + x^1 + x^0 = 0x07)
fn build_crc8_table() -> [u8; 256]
{
    let mut table = [0u8; 256];
    for i in 0..256
    {
        let mut crc = i as u8;
        for _ in 0..8
        {
            if crc & 0x80 != 0
            {
                crc = (crc << 1) ^ 0x07;
            }
            else
            {
                crc <<= 1;
            }
        }
        table[i] = crc;
    }
    table
}

/// Compute CRC-8 checksum using FLAC polynomial
///
/// # Parameters
/// * `data` - data to checksum
///
/// # Returns
/// `u8` - CRC-8 checksum value
fn crc8(data: &[u8]) -> u8
{
    let table = build_crc8_table();
    let mut crc = 0u8;
    for &byte in data
    {
        crc = table[(crc ^ byte) as usize];
    }
    crc
}

/// Compute CRC-16 checksum for FLAC
///
/// # Parameters
/// * `data` - data to checksum
///
/// # Returns
/// `u16` - CRC-16 checksum value
///
/// # Notes
/// Uses polynomial x^16 + x^15 + x^2 + x^0 = 0x8005
fn crc16(data: &[u8]) -> u16
{
    let mut crc = 0u16;
    for &byte in data
    {
        crc = ((crc << 8) ^ crc16_table(((crc >> 8) ^ byte as u16) as u8)) & 0xFFFF;
    }
    crc
}

/// Generate CRC-16 table entry
///
/// # Parameters
/// * `val` - byte value to generate entry for
///
/// # Returns
/// `u16` - CRC-16 table entry
fn crc16_table(val: u8) -> u16
{
    let mut crc = (val as u16) << 8;
    for _ in 0..8
    {
        if crc & 0x8000 != 0
        {
            crc = (crc << 1) ^ 0x8005;
        }
        else
        {
            crc <<= 1;
        }
    }
    crc & 0xFFFF
}

/// MD5 context for computing audio checksum
struct MD5Context
{
    state: [u32; 4],
    count: [u32; 2],
    buffer: [u8; 64],
}

impl MD5Context
{
    /// Create new MD5 context
    ///
    /// # Returns
    /// `MD5Context` - initialized context
    fn new() -> Self
    {
        MD5Context
        {
            state: [0x67452301, 0xEFCDAB89, 0x98BADCFE, 0x10325476],
            count: [0, 0],
            buffer: [0; 64],
        }
    }

    /// Update MD5 hash with new data
    ///
    /// # Parameters
    /// * `data` - data to add to hash
    fn update(&mut self, data: &[u8])
    {
        let mut input_index = 0;
        let len = data.len();

        // compute number of bytes mod 64
        let index = (self.count[0] >> 3) as usize & 0x3F;

        // update number of bits
        self.count[0] = self.count[0].wrapping_add((len as u32) << 3);
        if self.count[0] < ((len as u32) << 3)
        {
            self.count[1] = self.count[1].wrapping_add(1);
        }
        self.count[1] = self.count[1].wrapping_add((len as u32) >> 29);

        let part_len = 64 - index;

        // transform as many times as possible
        if len >= part_len
        {
            self.buffer[index..index + part_len].copy_from_slice(&data[0..part_len]);
            self.transform(&self.buffer.clone());

            let mut i = part_len;
            while i + 63 < len
            {
                let mut chunk = [0u8; 64];
                chunk.copy_from_slice(&data[i..i + 64]);
                self.transform(&chunk);
                i += 64;
            }
            input_index = i;
        }

        // buffer remaining input
        if input_index < len
        {
            let remaining = len - input_index;
            let buffer_index = if input_index == 0 { index } else { 0 };
            self.buffer[buffer_index..buffer_index + remaining]
                .copy_from_slice(&data[input_index..]);
        }
    }

    /// Perform MD5 transform on a 64-byte block
    ///
    /// # Parameters
    /// * `block` - 64-byte block to transform
    ///
    /// # Notes
    /// Implements the four rounds of MD5 using auxiliary functions F, G, H, and I.
    /// Each round applies a specific nonlinear function and uses a subset of the
    /// message block in a particular order.
    fn transform(&mut self, block: &[u8; 64])
    {
        let mut a = self.state[0];
        let mut b = self.state[1];
        let mut c = self.state[2];
        let mut d = self.state[3];

        // decode the 64-byte block into 16 32-bit words (little-endian)
        let mut x = [0u32; 16];
        for i in 0..16
        {
            x[i] = u32::from_le_bytes([
                block[i * 4],
                block[i * 4 + 1],
                block[i * 4 + 2],
                block[i * 4 + 3],
            ]);
        }

        // Round 1: uses auxiliary function F(b, c, d) = (b & c) | (!b & d)
        // processes words in order: 0, 1, 2, 3, ..., 15
        // rotation amounts cycle through: 7, 12, 17, 22
        macro_rules! ff
        {
           ($a:expr, $b:expr, $c:expr, $d:expr, $x:expr, $s:expr, $ac:expr) =>
           {
               // F(b, c, d) = (b AND c) OR (NOT b AND d)
               // this selects bits from c where b is 1, and from d where b is 0
               $a = $a.wrapping_add((($b & $c) | (!$b & $d)).wrapping_add($x).wrapping_add($ac));
               // rotate left by $s bits and add b
               $a = $a.rotate_left($s).wrapping_add($b);
           };
       }

        // apply F function 16 times with different message words and constants
        // $ac values are derived from sine function: floor(2^32 * abs(sin(i)))
        ff!(a, b, c, d, x[0], 7, 0xD76AA478);
        ff!(d, a, b, c, x[1], 12, 0xE8C7B756);
        ff!(c, d, a, b, x[2], 17, 0x242070DB);
        ff!(b, c, d, a, x[3], 22, 0xC1BDCEEE);
        ff!(a, b, c, d, x[4], 7, 0xF57C0FAF);
        ff!(d, a, b, c, x[5], 12, 0x4787C62A);
        ff!(c, d, a, b, x[6], 17, 0xA8304613);
        ff!(b, c, d, a, x[7], 22, 0xFD469501);
        ff!(a, b, c, d, x[8], 7, 0x698098D8);
        ff!(d, a, b, c, x[9], 12, 0x8B44F7AF);
        ff!(c, d, a, b, x[10], 17, 0xFFFF5BB1);
        ff!(b, c, d, a, x[11], 22, 0x895CD7BE);
        ff!(a, b, c, d, x[12], 7, 0x6B901122);
        ff!(d, a, b, c, x[13], 12, 0xFD987193);
        ff!(c, d, a, b, x[14], 17, 0xA679438E);
        ff!(b, c, d, a, x[15], 22, 0x49B40821);

        // Round 2: uses auxiliary function G(b, c, d) = (b & d) | (c & !d)
        // processes words in order: 1, 6, 11, 0, 5, 10, 15, 4, 9, 14, 3, 8, 13, 2, 7, 12
        // rotation amounts cycle through: 5, 9, 14, 20
        macro_rules! gg
        {
           ($a:expr, $b:expr, $c:expr, $d:expr, $x:expr, $s:expr, $ac:expr) =>
           {
               // G(b, c, d) = (b AND d) OR (c AND NOT d)
               // this selects bits from b where d is 1, and from c where d is 0
               $a = $a.wrapping_add((($b & $d) | ($c & !$d)).wrapping_add($x).wrapping_add($ac));
               $a = $a.rotate_left($s).wrapping_add($b);
           };
       }

        // apply G function 16 times with message words accessed in a different pattern
        gg!(a, b, c, d, x[1], 5, 0xF61E2562);
        gg!(d, a, b, c, x[6], 9, 0xC040B340);
        gg!(c, d, a, b, x[11], 14, 0x265E5A51);
        gg!(b, c, d, a, x[0], 20, 0xE9B6C7AA);
        gg!(a, b, c, d, x[5], 5, 0xD62F105D);
        gg!(d, a, b, c, x[10], 9, 0x02441453);
        gg!(c, d, a, b, x[15], 14, 0xD8A1E681);
        gg!(b, c, d, a, x[4], 20, 0xE7D3FBC8);
        gg!(a, b, c, d, x[9], 5, 0x21E1CDE6);
        gg!(d, a, b, c, x[14], 9, 0xC33707D6);
        gg!(c, d, a, b, x[3], 14, 0xF4D50D87);
        gg!(b, c, d, a, x[8], 20, 0x455A14ED);
        gg!(a, b, c, d, x[13], 5, 0xA9E3E905);
        gg!(d, a, b, c, x[2], 9, 0xFCEFA3F8);
        gg!(c, d, a, b, x[7], 14, 0x676F02D9);
        gg!(b, c, d, a, x[12], 20, 0x8D2A4C8A);

        // Round 3: uses auxiliary function H(b, c, d) = b ^ c ^ d
        // processes words in order: 5, 8, 11, 14, 1, 4, 7, 10, 13, 0, 3, 6, 9, 12, 15, 2
        // rotation amounts cycle through: 4, 11, 16, 23
        macro_rules! hh
        {
           ($a:expr, $b:expr, $c:expr, $d:expr, $x:expr, $s:expr, $ac:expr) =>
           {
               // H(b, c, d) = b XOR c XOR d
               // this is a simple three-way XOR, providing good bit mixing
               $a = $a.wrapping_add(($b ^ $c ^ $d).wrapping_add($x).wrapping_add($ac));
               $a = $a.rotate_left($s).wrapping_add($b);
           };
       }

        // apply H function 16 times with yet another message word access pattern
        hh!(a, b, c, d, x[5], 4, 0xFFFA3942);
        hh!(d, a, b, c, x[8], 11, 0x8771F681);
        hh!(c, d, a, b, x[11], 16, 0x6D9D6122);
        hh!(b, c, d, a, x[14], 23, 0xFDE5380C);
        hh!(a, b, c, d, x[1], 4, 0xA4BEEA44);
        hh!(d, a, b, c, x[4], 11, 0x4BDECFA9);
        hh!(c, d, a, b, x[7], 16, 0xF6BB4B60);
        hh!(b, c, d, a, x[10], 23, 0xBEBFBC70);
        hh!(a, b, c, d, x[13], 4, 0x289B7EC6);
        hh!(d, a, b, c, x[0], 11, 0xEAA127FA);
        hh!(c, d, a, b, x[3], 16, 0xD4EF3085);
        hh!(b, c, d, a, x[6], 23, 0x04881D05);
        hh!(a, b, c, d, x[9], 4, 0xD9D4D039);
        hh!(d, a, b, c, x[12], 11, 0xE6DB99E5);
        hh!(c, d, a, b, x[15], 16, 0x1FA27CF8);
        hh!(b, c, d, a, x[2], 23, 0xC4AC5665);

        // Round 4: uses auxiliary function I(b, c, d) = c ^ (b | !d)
        // processes words in order: 0, 7, 14, 5, 12, 3, 10, 1, 8, 15, 6, 13, 4, 11, 2, 9
        // rotation amounts cycle through: 6, 10, 15, 21
        macro_rules! ii
        {
           ($a:expr, $b:expr, $c:expr, $d:expr, $x:expr, $s:expr, $ac:expr) =>
           {
               // I(b, c, d) = c XOR (b OR NOT d)
               // this provides additional nonlinearity for the final round
               $a = $a.wrapping_add(($c ^ ($b | !$d)).wrapping_add($x).wrapping_add($ac));
               $a = $a.rotate_left($s).wrapping_add($b);
           };
       }

        // apply I function 16 times completing the MD5 transformation
        ii!(a, b, c, d, x[0], 6, 0xF4292244);
        ii!(d, a, b, c, x[7], 10, 0x432AFF97);
        ii!(c, d, a, b, x[14], 15, 0xAB9423A7);
        ii!(b, c, d, a, x[5], 21, 0xFC93A039);
        ii!(a, b, c, d, x[12], 6, 0x655B59C3);
        ii!(d, a, b, c, x[3], 10, 0x8F0CCC92);
        ii!(c, d, a, b, x[10], 15, 0xFFEFF47D);
        ii!(b, c, d, a, x[1], 21, 0x85845DD1);
        ii!(a, b, c, d, x[8], 6, 0x6FA87E4F);
        ii!(d, a, b, c, x[15], 10, 0xFE2CE6E0);
        ii!(c, d, a, b, x[6], 15, 0xA3014314);
        ii!(b, c, d, a, x[13], 21, 0x4E0811A1);
        ii!(a, b, c, d, x[4], 6, 0xF7537E82);
        ii!(d, a, b, c, x[11], 10, 0xBD3AF235);
        ii!(c, d, a, b, x[2], 15, 0x2AD7D2BB);
        ii!(b, c, d, a, x[9], 21, 0xEB86D391);

        // add the transformed values back to the state (modulo 2^32)
        // this ensures each block's contribution is accumulated
        self.state[0] = self.state[0].wrapping_add(a);
        self.state[1] = self.state[1].wrapping_add(b);
        self.state[2] = self.state[2].wrapping_add(c);
        self.state[3] = self.state[3].wrapping_add(d);
    }

    /// Finalize MD5 hash and return digest
    ///
    /// # Returns
    /// `[u8; 16]` - MD5 digest
    fn finalize(&mut self) -> [u8; 16]
    {
        let mut bits = [0u8; 8];
        for i in 0..2
        {
            bits[i * 4..i * 4 + 4].copy_from_slice(&self.count[i].to_le_bytes());
        }

        // pad to 56 bytes mod 64
        let index = (self.count[0] >> 3) as usize & 0x3F;
        let pad_len = if index < 56 { 56 - index } else { 120 - index };
        let mut padding = vec![0u8; pad_len];
        padding[0] = 0x80;
        self.update(&padding);

        // append length before final transform
        self.update(&bits);

        // store state in digest
        let mut digest = [0u8; 16];
        for i in 0..4
        {
            digest[i * 4..i * 4 + 4].copy_from_slice(&self.state[i].to_le_bytes());
        }
        digest
    }
}

/// Compute MD5 checksum of audio samples
///
/// # Parameters
/// * `samples` - audio samples as i16 values
///
/// # Returns
/// `[u8; 16]` - MD5 digest of audio data
///
/// # Notes
/// Samples are processed in little-endian byte order as required by FLAC spec
fn compute_md5(samples: &[i16]) -> [u8; 16]
{
    let mut ctx = MD5Context::new();

    // process samples in little-endian byte order
    // for FLAC, samples are interleaved and sign-extended if needed
    for &sample in samples
    {
        let bytes = sample.to_le_bytes();
        ctx.update(&bytes);
    }

    ctx.finalize()
}

/// Bit writer for FLAC encoding
struct BitWriter
{
    buffer: Vec<u8>,
    current_byte: u8,
    bit_count: u8,
}

impl BitWriter
{
    /// Create new bit writer
    ///
    /// # Returns
    /// `BitWriter` - initialized bit writer
    fn new() -> Self
    {
        BitWriter
        {
            buffer: Vec::new(),
            current_byte: 0,
            bit_count: 0,
        }
    }

    /// Write specified number of bits to the stream
    ///
    /// # Parameters
    /// * `value` - value to write
    /// * `bits` - number of bits to write
    fn write_bits(&mut self, value: u64, bits: u8)
    {
        let mut bits_remaining = bits;

        while bits_remaining > 0
        {
            let bits_to_write = std::cmp::min(8 - self.bit_count, bits_remaining);
            let shift = bits_remaining - bits_to_write;

            // handle the mask carefully to avoid overflow
            let mask = if bits_to_write >= 64
            {
                u64::MAX
            }
            else
            {
                ((1u64 << bits_to_write) - 1)
            };

            let bits_value = if shift >= 64
            {
                0u8
            }
            else
            {
                ((value >> shift) & mask) as u8
            };

            self.current_byte |= bits_value << (8 - self.bit_count - bits_to_write);
            self.bit_count += bits_to_write;

            if self.bit_count == 8
            {
                self.buffer.push(self.current_byte);
                self.current_byte = 0;
                self.bit_count = 0;
            }

            bits_remaining -= bits_to_write;
        }
    }

    /// Write a single byte
    ///
    /// # Parameters
    /// * `byte` - byte to write
    fn write_byte(&mut self, byte: u8)
    {
        self.write_bits(byte as u64, 8);
    }

    /// Write multiple bytes
    ///
    /// # Parameters
    /// * `bytes` - slice of bytes to write
    fn write_bytes(&mut self, bytes: &[u8])
    {
        for &byte in bytes
        {
            self.write_byte(byte);
        }
    }

    /// Write unary-encoded value
    ///
    /// # Parameters
    /// * `value` - value to encode
    ///
    /// # Notes
    /// Writes 'value' zeros followed by a one
    fn write_unary(&mut self, value: u32)
    {
        for _ in 0..value
        {
            self.write_bits(0, 1);
        }
        self.write_bits(1, 1);
    }

    /// Align to byte boundary by flushing partial byte
    fn byte_align(&mut self)
    {
        if self.bit_count > 0
        {
            self.buffer.push(self.current_byte);
            self.current_byte = 0;
            self.bit_count = 0;
        }
    }

    /// Get all bytes written so far
    ///
    /// # Returns
    /// `Vec<u8>` - complete byte buffer including partial byte if any
    fn get_bytes(&self) -> Vec<u8>
    {
        let mut result = self.buffer.clone();
        if self.bit_count > 0
        {
            result.push(self.current_byte);
        }
        result
    }
}

/// Write UTF-8 encoded number for frame header
///
/// # Parameters
/// * `writer` - bit writer to write to
/// * `value` - value to encode
///
/// # Notes
/// FLAC uses UTF-8 encoding for frame/sample numbers to support
/// large file sizes efficiently
fn write_utf8_number(writer: &mut BitWriter, value: u64)
{
    // 1-byte encoding: 0xxxxxxx
    // range: 0 to 127 (0x7F)
    if value < 0x80
    {
        writer.write_byte(value as u8);
    }

    // 2-byte encoding: 110xxxxx 10xxxxxx
    // range: 128 to 2047 (0x7FF)
    // first byte: 0xC0 (110 00000) | top 5 bits of value
    // second byte: 0x80 (10 000000) | bottom 6 bits of value
    else if value < 0x800
    {
        writer.write_byte(0xC0 | ((value >> 6) & 0x1F) as u8);
        writer.write_byte(0x80 | (value & 0x3F) as u8);
    }

    // 3-byte encoding: 1110xxxx 10xxxxxx 10xxxxxx
    // range: 2048 to 65535 (0xFFFF)
    // first byte: 0xE0 (1110 0000) | top 4 bits
    // second byte: 0x80 | middle 6 bits
    // third byte: 0x80 | bottom 6 bits
    else if value < 0x10000
    {
        writer.write_byte(0xE0 | ((value >> 12) & 0x0F) as u8);
        writer.write_byte(0x80 | ((value >> 6) & 0x3F) as u8);
        writer.write_byte(0x80 | (value & 0x3F) as u8);
    }

    // 4-byte encoding: 11110xxx 10xxxxxx 10xxxxxx 10xxxxxx
    // range: 65536 to 2097151 (0x1FFFFF)
    // first byte: 0xF0 (11110 000) | top 3 bits
    // remaining bytes: 0x80 | 6 bits each
    else if value < 0x200000
    {
        writer.write_byte(0xF0 | ((value >> 18) & 0x07) as u8);
        writer.write_byte(0x80 | ((value >> 12) & 0x3F) as u8);
        writer.write_byte(0x80 | ((value >> 6) & 0x3F) as u8);
        writer.write_byte(0x80 | (value & 0x3F) as u8);
    }

    // 5-byte encoding: 111110xx 10xxxxxx 10xxxxxx 10xxxxxx 10xxxxxx
    // range: 2097152 to 67108863 (0x3FFFFFF)
    // first byte: 0xF8 (111110 00) | top 2 bits
    // remaining bytes: 0x80 | 6 bits each
    else if value < 0x4000000
    {
        writer.write_byte(0xF8 | ((value >> 24) & 0x03) as u8);
        writer.write_byte(0x80 | ((value >> 18) & 0x3F) as u8);
        writer.write_byte(0x80 | ((value >> 12) & 0x3F) as u8);
        writer.write_byte(0x80 | ((value >> 6) & 0x3F) as u8);
        writer.write_byte(0x80 | (value & 0x3F) as u8);
    }

    // 6-byte encoding: 1111110x 10xxxxxx 10xxxxxx 10xxxxxx 10xxxxxx 10xxxxxx
    // range: 67108864 to 2147483647 (0x7FFFFFFF)
    // first byte: 0xFC (1111110 0) | top 1 bit
    // remaining bytes: 0x80 | 6 bits each
    else if value < 0x80000000
    {
        writer.write_byte(0xFC | ((value >> 30) & 0x01) as u8);
        writer.write_byte(0x80 | ((value >> 24) & 0x3F) as u8);
        writer.write_byte(0x80 | ((value >> 18) & 0x3F) as u8);
        writer.write_byte(0x80 | ((value >> 12) & 0x3F) as u8);
        writer.write_byte(0x80 | ((value >> 6) & 0x3F) as u8);
        writer.write_byte(0x80 | (value & 0x3F) as u8);
    }

    // 7-byte encoding: 11111110 10xxxxxx 10xxxxxx 10xxxxxx 10xxxxxx 10xxxxxx 10xxxxxx
    // range: 2147483648 and above
    // first byte: 0xFE (11111110) with no value bits
    // remaining bytes: 0x80 | 6 bits each, covering up to 36 bits total
    else
    {
        writer.write_byte(0xFE);
        writer.write_byte(0x80 | ((value >> 30) & 0x3F) as u8);
        writer.write_byte(0x80 | ((value >> 24) & 0x3F) as u8);
        writer.write_byte(0x80 | ((value >> 18) & 0x3F) as u8);
        writer.write_byte(0x80 | ((value >> 12) & 0x3F) as u8);
        writer.write_byte(0x80 | ((value >> 6) & 0x3F) as u8);
        writer.write_byte(0x80 | (value & 0x3F) as u8);
    }
}

/// Apply fixed predictor of given order
///
/// # Parameters
/// * `samples` - input samples
/// * `order` - predictor order (0-4)
///
/// # Returns
/// `Vec<i32>` - residual values after prediction
///
/// # Notes
/// The first 'order' values in the returned vector are zeros (warm-up samples
/// are stored separately in the subframe header)
fn apply_fixed_predictor(samples: &[i32], order: usize) -> Vec<i32>
{
    let mut residual = Vec::with_capacity(samples.len());

    // for fixed predictor, the entire residual array is returned
    // but only samples after 'order' are actual residuals

    // apply predictor to all samples
    for i in 0..samples.len()
    {
        if i < order
        {
            // warm-up samples aren't predicted, they're stored in the subframe header
            residual.push(0); // these will be ignored during encoding
        }
        else
        {
            let predicted = match order
            {
                0 => 0,
                1 => samples[i - 1],
                2 => 2 * samples[i - 1] - samples[i - 2],
                3 => 3 * samples[i - 1] - 3 * samples[i - 2] + samples[i - 3],
                4 => 4 * samples[i - 1] - 6 * samples[i - 2] + 4 * samples[i - 3] - samples[i - 4],
                _ => return residual, // invalid order
            };
            residual.push(samples[i] - predicted);
        }
    }

    residual
}

/// Calculate the best Rice parameter for a partition
///
/// # Parameters
/// * `residual` - residual values to analyze
///
/// # Returns
/// `u32` - optimal Rice parameter (0-14)
///
/// # Notes
/// Estimates the parameter based on mean absolute deviation. The optimal
/// parameter is roughly log2(mean * 0.75)
fn calculate_rice_parameter(residual: &[i32]) -> u32
{
    if residual.is_empty()
    {
        return 0;
    }

    // calculate mean of absolute values
    let sum: u64 = residual.iter().map(|&x| x.unsigned_abs() as u64).sum();
    let mean = sum / residual.len() as u64;

    if mean == 0
    {
        return 0;
    }

    let mut param = 0u32;
    let mut test_mean = mean;

    while test_mean > 0 && param < MAX_RICE_PARAM_4BIT
    {
        test_mean >>= 1;
        if test_mean > 0
        {
            param += 1;
        }
    }

    // adjust for better compression
    if param > 0 && mean < (1 << (param - 1))
    {
        param -= 1;
    }

    param.min(MAX_RICE_PARAM_4BIT)
}

/// Encode residual using Rice coding
///
/// # Parameters
/// * `writer` - bit writer to write to
/// * `residual` - residual values to encode
/// * `rice_param` - Rice parameter to use
///
/// # Returns
/// `Result<()>` - Ok if successful
///
/// # Notes
/// Uses zigzag encoding to map signed values to unsigned, then encodes
/// with unary MSB and binary LSB
fn encode_rice_partition(writer: &mut BitWriter, residual: &[i32], rice_param: u32) -> Result<()>
{
    for &sample in residual
    {
        // zigzag encode (fold) the residual - mapping signed to unsigned
        let folded = if sample >= 0
        {
            (sample as u32) << 1
        }
        else
        {
            (((-(sample + 1)) as u32) << 1) | 1
        };

        // split into MSB and LSB parts
        let msb = folded >> rice_param;
        let lsb = folded & ((1 << rice_param) - 1);

        // write unary-encoded MSB (zeros followed by a one)
        writer.write_unary(msb);

        // write binary-encoded LSB
        if rice_param > 0
        {
            writer.write_bits(lsb as u64, rice_param as u8);
        }
    }

    Ok(())
}

/// Encode residual with partitioned Rice coding
///
/// # Parameters
/// * `writer` - bit writer to write to
/// * `residual` - residual values to encode
/// * `predictor_order` - order of predictor used
/// * `block_size` - size of audio block
/// * `compression_level` - compression level (0-8)
///
/// # Returns
/// `Result<()>` - Ok if successful
///
/// # Notes
/// Higher compression levels use more partitions for better compression at
/// the cost of encoding speed
fn encode_residual(writer: &mut BitWriter, residual: &[i32], predictor_order: usize, block_size: usize, compression_level: u8) -> Result<()>
{
    // calculate partition order based on compression level
    let mut partition_order = match compression_level
    {
        0 => 0,
        1..=2 => 2.min((block_size.trailing_zeros()).min(8)),
        3..=5 => 4.min((block_size.trailing_zeros()).min(8)),
        6..=8 => 6.min((block_size.trailing_zeros()).min(8)),
        _ => 6.min((block_size.trailing_zeros()).min(8)),
    };

    // ensure valid partition order
    while partition_order > 0
    {
        let partition_samples = block_size >> partition_order;
        if partition_samples > predictor_order && partition_samples >= 4
        {
            break;
        }
        partition_order -= 1;
    }

    // write coding method (0b00 for 4-bit Rice parameters)
    writer.write_bits(0, 2);

    // write partition order
    writer.write_bits(partition_order as u64, 4);

    let num_partitions = 1 << partition_order;
    let default_partition_samples = block_size >> partition_order;

    let mut sample_idx = 0;
    for partition_idx in 0..num_partitions
    {
        // first partition has fewer samples due to predictor order
        let partition_samples = if partition_idx == 0
        {
            default_partition_samples - predictor_order
        }
        else
        {
            default_partition_samples
        };

        if partition_samples == 0
        {
            continue;
        }

        let partition_residual = &residual[sample_idx..sample_idx + partition_samples];
        sample_idx += partition_samples;

        // calculate best Rice parameter for this partition
        let rice_param = calculate_rice_parameter(partition_residual);

        if rice_param > MAX_RICE_PARAM_4BIT
        {
            // use escape code for incompressible data
            writer.write_bits(0xF, 4); // escape code (all ones)

            // calculate bits needed for raw samples
            let mut max_val = 0u32;
            for &sample in partition_residual
            {
                max_val = max_val.max(sample.unsigned_abs());
            }

            let mut bits_needed = 1u32; // at least 1 bit for sign
            while (1u32 << bits_needed) <= max_val && bits_needed < 32
            {
                bits_needed += 1;
            }
            bits_needed += 1; // add sign bit
            bits_needed = bits_needed.max(1).min(32);

            // write bits per sample minus 1
            writer.write_bits((bits_needed - 1) as u64, 5);

            // write samples as raw signed integers
            for &sample in partition_residual
            {
                // write as signed value with calculated bit width
                writer.write_bits(sample as u32 as u64, bits_needed as u8);
            }
        }
        else
        {
            // write Rice parameter
            writer.write_bits(rice_param as u64, 4);

            // encode partition with Rice coding
            encode_rice_partition(writer, partition_residual, rice_param)?;
        }
    }

    Ok(())
}

/// Encode a subframe
///
/// # Parameters
/// * `writer` - bit writer to write to
/// * `samples` - audio samples for this channel
/// * `bits_per_sample` - bits per sample
/// * `compression_level` - compression level (0-8)
///
/// # Returns
/// `Result<()>` - Ok if successful
///
/// # Notes
/// Chooses between verbatim (no prediction) and fixed predictor based on
/// compression level
fn encode_subframe(writer: &mut BitWriter, samples: &[i32], bits_per_sample: u8, compression_level: u8) -> Result<()>
{
    let block_size = samples.len();

    // choose predictor order based on compression level
    let predictor_order = match compression_level
    {
        0 => 0, // verbatim (no prediction)
        1 => if block_size >= 1 { 1 } else { 0 },
        2 => if block_size >= 2 { 2 } else { 0 },
        3..=4 => if block_size >= 3 { 3 } else { 0 },
        5..=8 => if block_size >= 4 { 4 } else { 0 },
        _ => if block_size >= 4 { 4 } else { 0 },
    };

    // write subframe header
    // bits 0: zero bit
    writer.write_bits(0, 1);

    // bits 1-6: subframe type
    if predictor_order == 0
    {
        // verbatim subframe
        writer.write_bits(0b000001, 6);
    }
    else
    {
        // fixed predictor subframe
        let subframe_type = 0b001000 | (predictor_order as u64);
        writer.write_bits(subframe_type as u64, 6);
    }

    // bit 7: no wasted bits
    writer.write_bits(0, 1);

    if predictor_order == 0
    {
        // verbatim subframe - write samples directly
        for &sample in samples
        {
            writer.write_bits(sample as u64, bits_per_sample);
        }
    }
    else
    {
        // write warm-up samples
        for i in 0..predictor_order
        {
            writer.write_bits(samples[i] as u64, bits_per_sample);
        }

        // calculate and encode residual
        let residual = apply_fixed_predictor(samples, predictor_order);
        // pass only the residual values after warm-up samples
        encode_residual(writer, &residual[predictor_order..], predictor_order, block_size, compression_level)?;
    }

    Ok(())
}

/// Encode a frame
///
/// # Parameters
/// * `writer` - bit writer to write to
/// * `samples` - interleaved audio samples
/// * `channels` - number of channels
/// * `sample_rate` - sample rate in Hz
/// * `bits_per_sample` - bits per sample
/// * `frame_number` - frame number for header
/// * `block_size` - number of samples per channel in this frame
/// * `compression_level` - compression level (0-8)
///
/// # Returns
/// `Result<()>` - Ok if successful
///
/// # Notes
/// Encodes a complete FLAC frame with header, subframes, and CRC
fn encode_frame(
    writer: &mut BitWriter,
    samples: &[i16],
    channels: u16,
    sample_rate: u32,
    bits_per_sample: u8,
    frame_number: u32,
    block_size: usize,
    compression_level: u8,
) -> Result<()>
{
    let frame_start = writer.buffer.len();

    // Frame header
    // sync code: 0b11111111111111 (14 bits)
    writer.write_bits(FRAME_SYNC_CODE as u64, 14);

    // reserved bit: 0
    writer.write_bits(0, 1);

    // blocking strategy: 0 (fixed block size)
    writer.write_bits(0, 1);

    // block size bits
    let block_size_bits = match block_size
    {
        192 => 0b0001,
        576 => 0b0010,
        1152 => 0b0011,
        2304 => 0b0100,
        4608 => 0b0101,
        256 => 0b1000,
        512 => 0b1001,
        1024 => 0b1010,
        2048 => 0b1011,
        4096 => 0b1100,
        8192 => 0b1101,
        16384 => 0b1110,
        32768 => 0b1111,
        _ =>
        {
            // uncommon block size
            if block_size < 256
            {
                0b0110
            }
            else
            {
                0b0111
            }
        }
    };
    writer.write_bits(block_size_bits, 4);

    // sample rate bits
    let sample_rate_bits = match sample_rate
    {
        88200 => 0b0001,
        176400 => 0b0010,
        192000 => 0b0011,
        8000 => 0b0100,
        16000 => 0b0101,
        22050 => 0b0110,
        24000 => 0b0111,
        32000 => 0b1000,
        44100 => 0b1001,
        48000 => 0b1010,
        96000 => 0b1011,
        _ => 0b0000, // get from streaminfo
    };
    writer.write_bits(sample_rate_bits, 4);

    // channel assignment
    let channel_bits = if channels == 1
    {
        0b0000 // mono
    }
    else if channels == 2
    {
        0b0001 // stereo (left, right)
    }
    else
    {
        (channels - 1) as u32 // multi-channel
    };
    writer.write_bits(channel_bits as u64, 4);

    // sample size bits
    let sample_size_bits = match bits_per_sample
    {
        8 => 0b001,
        12 => 0b010,
        16 => 0b100,
        20 => 0b101,
        24 => 0b110,
        _ => 0b000, // get from streaminfo
    };
    writer.write_bits(sample_size_bits, 3);

    // reserved bit: 0
    writer.write_bits(0, 1);

    // frame/sample number (UTF-8 encoded)
    write_utf8_number(writer, frame_number as u64);

    // uncommon block size (if needed)
    if block_size_bits == 0b0110
    {
        writer.write_byte((block_size - 1) as u8);
    }
    else if block_size_bits == 0b0111
    {
        writer.write_bits((block_size - 1) as u64, 16);
    }

    // frame header CRC-8
    // we need to get all header bytes including any partial byte
    let mut header_bytes = writer.buffer[frame_start..].to_vec();
    if writer.bit_count > 0
    {
        header_bytes.push(writer.current_byte);
    }
    let crc8_value = crc8(&header_bytes);
    writer.write_byte(crc8_value);

    // encode subframes
    let mut channel_samples = vec![vec![0i32; block_size]; channels as usize];

    // deinterleave samples
    for i in 0..block_size
    {
        for ch in 0..channels as usize
        {
            let sample_idx = i * channels as usize + ch;
            if sample_idx < samples.len()
            {
                channel_samples[ch][i] = samples[sample_idx] as i32;
            }
        }
    }

    // encode each channel
    for ch in 0..channels as usize
    {
        encode_subframe(writer, &channel_samples[ch], bits_per_sample, compression_level)?;
    }

    // byte-align
    writer.byte_align();

    // frame footer (CRC-16)
    // CRC-16 covers the entire frame from sync code to just before the CRC itself
    let frame_bytes = &writer.buffer[frame_start..];
    let crc16_value = crc16(frame_bytes);
    writer.write_bits(crc16_value as u64, 16);

    Ok(())
}

/// Write streaminfo metadata block
///
/// # Parameters
/// * `writer` - bit writer to write to
/// * `min_block_size` - minimum block size in samples
/// * `max_block_size` - maximum block size in samples
/// * `min_frame_size` - minimum frame size in bytes (0 if unknown)
/// * `max_frame_size` - maximum frame size in bytes (0 if unknown)
/// * `sample_rate` - sample rate in Hz
/// * `channels` - number of channels
/// * `bits_per_sample` - bits per sample
/// * `total_samples` - total samples per channel
/// * `md5` - MD5 digest of unencoded audio data
fn write_streaminfo(
    writer: &mut BitWriter,
    min_block_size: u16,
    max_block_size: u16,
    min_frame_size: u32,
    max_frame_size: u32,
    sample_rate: u32,
    channels: u16,
    bits_per_sample: u8,
    total_samples: u64,
    md5: [u8; 16],
)
{
    // metadata block header
    // last metadata block flag: 1
    writer.write_bits(1, 1);
    // block type: 0 (streaminfo)
    writer.write_bits(0, 7);
    // length: 34 bytes
    writer.write_bits(34, 24);

    // streaminfo data
    writer.write_bits(min_block_size as u64, 16);
    writer.write_bits(max_block_size as u64, 16);
    writer.write_bits(min_frame_size as u64, 24);
    writer.write_bits(max_frame_size as u64, 24);
    writer.write_bits(sample_rate as u64, 20);
    writer.write_bits((channels - 1) as u64, 3);
    writer.write_bits((bits_per_sample - 1) as u64, 5);
    writer.write_bits(total_samples, 36);

    // MD5 checksum
    for byte in md5
    {
        writer.write_byte(byte);
    }
}

/// Main FLAC encoding function with compression level
///
/// # Parameters
/// * `samples` - audio samples as f32 values
/// * `sample_rate` - sample rate in Hz
/// * `channels` - number of channels
/// * `compression_level` - compression level (0=fastest, 8=best)
///
/// # Returns
/// `Result<Vec<u8>>` - encoded FLAC data
///
/// # Errors
/// Returns error if fewer than 16 samples per channel or invalid compression level
pub fn encode_flac_with_level(
    samples: &[f32],
    sample_rate: u32,
    channels: u16,
    compression_level: u8,
) -> Result<Vec<u8>>
{
    // convert f32 samples to i16
    let i16_samples: Vec<i16> = samples
        .iter()
        .map(|&s| (s * 32767.0).clamp(-32768.0, 32767.0) as i16)
        .collect();

    let total_samples = i16_samples.len() / channels as usize;

    // FLAC requires at least 16 samples per channel
    if total_samples < 16
    {
        return Err(anyhow!(
            "FLAC requires at least 16 samples per channel, got {}",
            total_samples
        ));
    }

    // validate compression level
    if compression_level > 8
    {
        return Err(anyhow!(
            "Invalid compression level {}, must be 0-8",
            compression_level
        ));
    }

    let bits_per_sample = 16u8;

    // choose block size based on compression level
    let block_size = match compression_level
    {
        0 => 1152,  // fast encoding
        1 => 1152,
        2 => 1152,
        3 => 4096,
        4 => 4096,
        5 => 4096,  // default
        6 => 4096,
        7 => 4096,
        8 => 4096,  // maximum compression
        _ => 4096,
    }.min(total_samples).max(16);


    let mut writer = BitWriter::new();

    // write FLAC signature
    writer.write_bytes(&FLAC_SIGNATURE);

    // calculate MD5 checksum of audio data
    let md5 = compute_md5(&i16_samples);

    // write streaminfo
    write_streaminfo(
        &mut writer,
        block_size as u16,
        block_size as u16,
        0, // unknown min frame size
        0, // unknown max frame size
        sample_rate,
        channels,
        bits_per_sample,
        total_samples as u64,
        md5,
    );

    // encode frames
    let mut sample_offset = 0;
    let mut frame_number = 0u32;

    while sample_offset < i16_samples.len()
    {
        let remaining = i16_samples.len() - sample_offset;
        let current_block_size = block_size.min(remaining / channels as usize);

        if current_block_size == 0
        {
            break;
        }

        let frame_samples = &i16_samples[sample_offset..sample_offset + current_block_size * channels as usize];

        encode_frame(
            &mut writer,
            frame_samples,
            channels,
            sample_rate,
            bits_per_sample,
            frame_number,
            current_block_size,
            compression_level,
        )?;

        sample_offset += current_block_size * channels as usize;
        frame_number += 1;
    }

    Ok(writer.get_bytes())
}

/// Export audio to FLAC file with specific compression level
///
/// # Parameters
/// * `path` - output file path
/// * `samples` - audio samples as f32 values
/// * `sample_rate` - sample rate in Hz
/// * `channels` - number of channels
/// * `compression_level` - compression level (0=fastest, 8=best)
///
/// # Returns
/// `Result<()>` - Ok if successful
pub fn export_to_flac_with_level(
    path: &Path,
    samples: &[f32],
    sample_rate: u32,
    channels: u16,
    compression_level: u8,
) -> Result<()>
{
    let flac_data = encode_flac_with_level(samples, sample_rate, channels, compression_level)?;
    let mut file = std::fs::File::create(path)?;
    file.write_all(&flac_data)?;
    Ok(())
}