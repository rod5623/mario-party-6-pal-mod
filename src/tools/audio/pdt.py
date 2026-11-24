"""Read MP6_Str.pdt (the streamed music archive) and append new tracks.

The game plays a track by its index in this file: HuAudSStreamPlay(id) -> msmStreamPlay(id) indexes the id table
directly, and msmStreamInit sizes every table from this header, so appended tracks need no code changes.

Layout (big-endian; every retail track is 32000 Hz stereo DSP ADPCM):
  0x00 u16 version (1), u16 track count, u32 4, u32 32000, u32 2,
       u32 id table offset (0x20), u32 coefficient table offset, u32 track header offset, u32 audio data offset
  id table:    u32 per track = file offset of its track header (padded to 32 bytes)
  coefficients: 32 bytes per channel (16 s16 DSP coefficients); track i uses sets 2i (left) and 2i+1 (right)
  track header, 0x20 bytes: u8 flags (1 = once, 3 = loops), u8 volume, u8 pan (0x40 = centre), u8 0,
       u32 sample rate, u32 nibble count (DSP num_nibbles), u32 loop start (DSP nibble address; 2 = sample 0),
       u32 left data offset, u16 left coefficient set, u16 0, u32 right data offset, u16 right set, u16 0
  audio data:  per track the left channel's DSP frames then the right's, each padded to 4 bytes.
"""
import struct

HEADER = ">HHIIIIIII"
TRACK = ">BBBBIIIIHHIHH"
TRACK_SIZE = 0x20
COEF_SIZE = 0x20


def align(n, to):
    return n + (-n % to)


class Track:
    def __init__(self, flags, volume, pan, rate, nibbles, loop_start, left, right, coefs):
        self.flags, self.volume, self.pan, self.rate = flags, volume, pan, rate
        self.nibbles, self.loop_start = nibbles, loop_start
        self.left, self.right = left, right      # channel data bytes
        self.coefs = coefs                        # (left 32 bytes, right 32 bytes)


def parse_dsp(blob):
    """A mono .dsp (standard 0x60-byte header) -> (nibbles, loop_flag, loop_start, coefs, data, rate, samples)."""
    samples, nibbles, rate = struct.unpack_from(">III", blob, 0)
    loop_flag, fmt, loop_start, loop_end, cur = struct.unpack_from(">HHIII", blob, 0x0C)
    if fmt != 0:
        raise ValueError("not DSP ADPCM")
    coefs = blob[0x1C:0x3C]
    data = blob[0x60:0x60 + (nibbles + 1) // 2]
    return nibbles, loop_flag, loop_start, coefs, data, rate, samples


def track_from_dsp(left_blob, right_blob, volume=0x61, pan=0x40):
    ln, lflag, lstart, lcoef, ldata, rate, _ = parse_dsp(left_blob)
    rn, rflag, rstart, rcoef, rdata, rrate, _ = parse_dsp(right_blob)
    if (ln, lflag, lstart, rate) != (rn, rflag, rstart, rrate):
        raise ValueError("left and right channels differ in length, loop or rate")
    return Track(3 if lflag else 1, volume, pan, rate, ln, lstart if lflag else 2, ldata, rdata, (lcoef, rcoef))


def read_header(path):
    with open(path, "rb") as f:
        head = f.read(0x40)
    return struct.unpack_from(HEADER, head, 0)


def append_tracks(src_path, dst_path, tracks):
    """Copy the archive at src_path to dst_path with `tracks` appended (ids count, count+1, ...)."""
    with open(src_path, "rb") as f:
        src = f.read()
    version, count, a, rate, b, ids_off, coef_off, hdr_off, data_off = struct.unpack_from(HEADER, src, 0)
    if version != 1:
        raise ValueError("unexpected PDT version")
    ids = [struct.unpack_from(">I", src, ids_off + 4 * i)[0] for i in range(count)]
    headers = [list(struct.unpack_from(TRACK, src, ids[i])) for i in range(count)]
    coefs = src[coef_off:coef_off + 2 * count * COEF_SIZE]
    data = src[data_off:]

    total = count + len(tracks)
    new_ids_off = 0x20
    new_coef_off = align(new_ids_off + 4 * total, 0x20)
    new_hdr_off = new_coef_off + 2 * total * COEF_SIZE
    new_data_off = align(new_hdr_off + total * TRACK_SIZE, 0x20)
    shift = new_data_off - data_off
    if shift % 32:
        raise ValueError("data shift must keep 32-byte alignment")

    out_data = bytearray(data)
    for h in headers:
        h[7] += shift   # left data offset
        h[10] += shift  # right data offset
    new_coefs = bytearray(coefs)
    for k, t in enumerate(tracks):
        index = count + k
        out_data += b"\0" * (-(new_data_off + len(out_data)) % 32)
        left = new_data_off + len(out_data)
        out_data += t.left + b"\0" * (-len(t.left) % 4)
        right = new_data_off + len(out_data)
        out_data += t.right + b"\0" * (-len(t.right) % 4)
        new_coefs += t.coefs[0] + t.coefs[1]
        headers.append([t.flags, t.volume, t.pan, 0, t.rate, t.nibbles, t.loop_start,
                        left, 2 * index, 0, right, 2 * index + 1, 0])

    out = bytearray(new_data_off)
    struct.pack_into(HEADER, out, 0, version, total, a, rate, b, new_ids_off, new_coef_off, new_hdr_off, new_data_off)
    for i in range(total):
        struct.pack_into(">I", out, new_ids_off + 4 * i, new_hdr_off + TRACK_SIZE * i)
        struct.pack_into(TRACK, out, new_hdr_off + TRACK_SIZE * i, *headers[i])
    out[new_coef_off:new_coef_off + len(new_coefs)] = new_coefs
    with open(dst_path, "wb") as f:
        f.write(out)
        f.write(out_data)
    return count  # id of the first appended track
