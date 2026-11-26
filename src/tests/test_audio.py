"""tools.audio: musyxextract round trip, pdt DSP parsing, scale_msm_volume ADPCM re-encoding."""
import math
import random
import struct

import pytest

from tools.audio import musyxextract as musyx
from tools.audio import pdt
from tools.audio.scale_msm_volume import clamp16, decode_frames, encode_frames

COEFS = [0, 0, 2048, 0, 3584, -1536, 3072, -1024, 4096, -2048, 1024, 0, 2560, -512, 3800, -1800]
COEF_BYTES = struct.pack(">16h", *COEFS)


# --- musyxextract ----------------------------------------------------------------------------

@pytest.mark.parametrize("samples, nibbles, size", [
    (0, 0, 0), (1, 3, 8), (13, 15, 8), (14, 16, 8), (15, 19, 16), (28, 32, 16), (100, 116, 64),
])
def test_sample_counts(samples, nibbles, size):
    # 14 samples per 8-byte frame (1 header byte + 7 data bytes = 16 nibbles); sizes round up to 8
    assert musyx.samples_to_nibbles(samples) == nibbles
    assert musyx.samples_to_bytes(samples) == size
    assert musyx.nibbles_to_samples(nibbles) == samples


def sdir_meta(i, sample_id, offset, samples, looped):
    """write_sdir's input: loop points in nibbles, ps/lps as 2-byte DSP header fields."""
    return {
        "id": sample_id, "offset": offset, "rate": 32000, "samples": samples,
        "loop_start": musyx.samples_to_nibbles(14) if looped else 0,
        "loop_end": musyx.samples_to_nibbles(samples) - 1 if looped else 0,
        "ps": bytes([0, 0x10 + i]), "lps": bytes([0, 0x20 + i]) if looped else b"\0\0",
        "lyn1": struct.pack(">h", 100 + i) if looped else b"\0\0",
        "lyn2": struct.pack(">h", -100 - i) if looped else b"\0\0",
        "coeffs": COEF_BYTES,
    }


def write_group(folder, name):
    """A two-sample .sdir/.samp pair; returns (sdir bytes, samp bytes, encoded sizes)."""
    rng = random.Random(7)
    lengths = (40, 70)       # samples
    meta, samp = {}, bytearray()
    for i, samples in enumerate(lengths):
        samp += b"\0" * (-len(samp) % 32)
        meta[i] = sdir_meta(i, 0x0100 + i, len(samp), samples, looped=i == 1)
        samp += bytes(rng.randrange(256) for _ in range(musyx.samples_to_bytes(samples)))
    with open(folder / f"{name}.sdir", "wb") as f:
        musyx.write_sdir(f, meta)
    (folder / f"{name}.samp").write_bytes(samp)
    encoded = [(musyx.samples_to_nibbles(n) + 1) // 2 for n in lengths]
    return (folder / f"{name}.sdir").read_bytes(), bytes(samp), meta, encoded


def test_extract_then_pack_round_trip(tmp_path):
    sound, dsps, packed = tmp_path / "sound", tmp_path / "dsp", tmp_path / "packed"
    for d in (sound, dsps, packed):
        d.mkdir()
    sdir, samp, meta, encoded = write_group(sound, "bank")

    musyx.extract_samples(str(sound), str(dsps))
    names = sorted(p.name for p in (dsps / "bank").iterdir())
    assert names == ["00000 (0x0100).dsp", "00001 (0x0101).dsp"]

    musyx.pack_samples(str(dsps / "bank"), str(packed))
    assert (packed / "bank.sdir").read_bytes() == sdir
    new_samp = (packed / "bank.samp").read_bytes()
    assert len(new_samp) == len(samp)
    for i, size in enumerate(encoded):
        start = meta[i]["offset"]
        assert new_samp[start:start + size] == samp[start:start + size]
        # pack zero-fills between the encoded size and the 8-byte-rounded sample size
        end = start + musyx.samples_to_bytes(meta[i]["samples"])
        assert new_samp[start + size:end] == b"\0" * (end - start - size)


def test_extracted_dsp_header(tmp_path):
    sound, dsps = tmp_path / "sound", tmp_path / "dsp"
    sound.mkdir()
    dsps.mkdir()
    write_group(sound, "bank")
    musyx.extract_samples(str(sound), str(dsps))
    blob = (dsps / "bank" / "00001 (0x0101).dsp").read_bytes()
    nibbles, loop_flag, loop_start, coefs, data, rate, samples = pdt.parse_dsp(blob)
    assert (samples, nibbles, rate, loop_flag) == (70, musyx.samples_to_nibbles(70), 32000, 1)
    assert loop_start == musyx.samples_to_nibbles(14)
    assert coefs == COEF_BYTES
    assert blob[0x3E:0x40] == b"\x00\x11"       # predictor/scale from the sdir


def test_pack_order_is_sorted(tmp_path):
    sound, dsps, packed = tmp_path / "sound", tmp_path / "dsp", tmp_path / "packed"
    for d in (sound, dsps, packed):
        d.mkdir()
    write_group(sound, "bank")
    musyx.extract_samples(str(sound), str(dsps))
    group = dsps / "bank"
    # recreate the files in reverse order so directory order (if unsorted) would differ
    files = sorted(group.iterdir())
    blobs = [(p.name, p.read_bytes()) for p in files]
    for p in files:
        p.unlink()
    for name, blob in reversed(blobs):
        (group / name).write_bytes(blob)
    musyx.pack_samples(str(group), str(packed))
    sdir = (packed / "bank.sdir").read_bytes()
    assert [struct.unpack_from(">H", sdir, 0x20 * i)[0] for i in range(2)] == [0x0100, 0x0101]


# --- pdt -------------------------------------------------------------------------------------

def make_dsp(samples, rate=32000, loop=False, payload=None):
    nibbles = musyx.samples_to_nibbles(samples)
    header = bytearray(0x60)
    struct.pack_into(">III", header, 0, samples, nibbles, rate)
    struct.pack_into(">HHIII", header, 0x0C, int(loop), 0, 2 if loop else 2, nibbles - 1 if loop else 0, 2)
    header[0x1C:0x3C] = COEF_BYTES
    data = payload if payload is not None else bytes(range((nibbles + 1) // 2))
    return bytes(header) + data


def test_parse_dsp():
    blob = make_dsp(28, loop=True) + b"trailing bytes are ignored"
    nibbles, loop_flag, loop_start, coefs, data, rate, samples = pdt.parse_dsp(blob)
    assert (nibbles, loop_flag, loop_start, rate, samples) == (32, 1, 2, 32000, 28)
    assert coefs == COEF_BYTES and data == bytes(range(16))


def test_parse_dsp_rejects_pcm():
    blob = bytearray(make_dsp(14))
    struct.pack_into(">H", blob, 0x0E, 1)
    with pytest.raises(ValueError):
        pdt.parse_dsp(bytes(blob))


def test_track_from_dsp():
    left, right = make_dsp(28, payload=b"L" * 16), make_dsp(28, payload=b"R" * 16)
    track = pdt.track_from_dsp(left, right)
    assert (track.flags, track.loop_start, track.nibbles, track.rate) == (1, 2, 32, 32000)
    assert (track.left, track.right) == (b"L" * 16, b"R" * 16)
    assert pdt.track_from_dsp(make_dsp(28, loop=True), make_dsp(28, loop=True)).flags == 3
    with pytest.raises(ValueError):
        pdt.track_from_dsp(make_dsp(28), make_dsp(42))


def test_append_tracks(tmp_path):
    first = pdt.track_from_dsp(make_dsp(28, payload=b"a" * 16), make_dsp(28, payload=b"b" * 16))
    empty = tmp_path / "empty.pdt"
    header = bytearray(0x20)
    struct.pack_into(pdt.HEADER, header, 0, 1, 0, 4, 32000, 2, 0x20, 0x20, 0x20, 0x20)
    empty.write_bytes(header)
    one, two = tmp_path / "one.pdt", tmp_path / "two.pdt"
    assert pdt.append_tracks(empty, one, [first]) == 0
    second = pdt.track_from_dsp(make_dsp(14, payload=b"c" * 8), make_dsp(14, payload=b"d" * 8))
    assert pdt.append_tracks(one, two, [second]) == 1

    data = two.read_bytes()
    version, count, *_, ids_off, coef_off, hdr_off, data_off = struct.unpack_from(pdt.HEADER, data, 0)
    assert (version, count) == (1, 2) and data_off % 32 == 0
    for index, (track, left, right) in enumerate([(first, b"a", b"b"), (second, b"c", b"d")]):
        header_at = struct.unpack_from(">I", data, ids_off + 4 * index)[0]
        h = struct.unpack_from(pdt.TRACK, data, header_at)
        assert h[5] == track.nibbles
        assert (h[8], h[11]) == (2 * index, 2 * index + 1)
        assert data[h[7]:h[7] + len(track.left)] == left * len(track.left)
        assert data[h[10]:h[10] + len(track.right)] == right * len(track.right)
        assert data[coef_off + 0x40 * index:coef_off + 0x40 * index + 0x20] == COEF_BYTES



def test_read_track_round_trip(tmp_path):
    first = pdt.track_from_dsp(make_dsp(28, payload=b"a" * 16), make_dsp(28, payload=b"b" * 16))
    second = pdt.track_from_dsp(make_dsp(14, loop=True, payload=b"c" * 8), make_dsp(14, loop=True, payload=b"d" * 8))
    empty = tmp_path / "empty.pdt"
    header = bytearray(0x20)
    struct.pack_into(pdt.HEADER, header, 0, 1, 0, 4, 32000, 2, 0x20, 0x20, 0x20, 0x20)
    empty.write_bytes(header)
    two = tmp_path / "two.pdt"
    pdt.append_tracks(empty, two, [first, second])
    blob = two.read_bytes()
    for index, track in enumerate((first, second)):
        read = pdt.read_track(blob, index)
        assert (read.flags, read.volume, read.pan, read.rate, read.nibbles, read.loop_start) ==             (track.flags, track.volume, track.pan, track.rate, track.nibbles, track.loop_start)
        assert (read.left, read.right, read.coefs) == (track.left, track.right, track.coefs)
    # a track read from one archive appends to another unchanged (how MP7 music is ported)
    copy = tmp_path / "copy.pdt"
    pdt.append_tracks(empty, copy, [pdt.read_track(blob, 1)])
    assert pdt.read_track(copy.read_bytes(), 0).left == second.left
    with pytest.raises(IndexError):
        pdt.read_track(blob, 2)

# --- scale_msm_volume ------------------------------------------------------------------------

def adpcm_frames(seed, frames=10):
    """DSP-ADPCM frames made by encoding a smooth, unclipped signal."""
    rng = random.Random(seed)
    amp, period = rng.choice([500, 4000, 12000, 20000]), rng.uniform(8, 60)
    signal = [int(amp * math.sin(2 * math.pi * i / period) + rng.uniform(-50, 50)) for i in range(14 * frames)]
    headers = [rng.randrange(8) << 4 for _ in range(frames)]
    data, _ = encode_frames(signal, headers, COEFS, 1.0)
    return data


@pytest.mark.parametrize("seed", range(12))
def test_reencode_at_unity_gain_is_exact(seed):
    # The bytes may differ (the encoder can pick a smaller scale), but the samples don't.
    data = adpcm_frames(seed)
    pcm, headers = decode_frames(data, 0, 10, COEFS)
    encoded, decoded = encode_frames(pcm, headers, COEFS, 1.0)
    assert decoded == pcm
    assert decode_frames(encoded, 0, 10, COEFS) == (decoded, [b for b in encoded[::8]])
    assert [h >> 4 for h in encoded[::8]] == [h >> 4 for h in headers]   # predictors kept


@pytest.mark.parametrize("seed", range(6))
def test_half_gain_halves_peaks(seed):
    pcm, headers = decode_frames(adpcm_frames(seed), 0, 10, COEFS)
    encoded, decoded = encode_frames(pcm, headers, COEFS, 0.5)
    assert len(encoded) == 80
    peak, new_peak = max(map(abs, pcm)), max(map(abs, decoded))
    assert abs(new_peak / peak - 0.5) < 0.03
    assert max(abs(a * 0.5 - b) for a, b in zip(pcm, decoded)) <= max(16, peak * 0.02)


@pytest.mark.parametrize("value, clamped", [
    (-32769, -32768), (-32768, -32768), (0, 0), (32767, 32767), (32768, 32767), (10 ** 6, 32767),
])
def test_clamp16(value, clamped):
    assert clamp16(value) == clamped
