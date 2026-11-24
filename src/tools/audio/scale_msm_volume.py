"""Lower the volume of the sample banks in a GSND/MSM archive (MP6_SND.msm).

Every DSP-ADPCM sample in every bank except the excluded ones is decoded,
multiplied by SFX_GAIN and re-encoded with its own coefficients and per-frame
predictors, so sample counts, loop points and bank sizes stay unchanged. The
SDIR initial/loop predictor-scale and loop history are updated to match.
The input archive is never modified; the output path must not exist.
"""
import argparse
import statistics
import struct
import sys
from pathlib import Path

from tools.audio.musyxextract import samples_to_bytes

SFX_GAIN = 0.80  # 0.80 is about -2 dB
EXCLUDED_BANKS = (0x000C, 0x000E)

HEADER_SIZE = 0x48
BANK_ENTRY_SIZE = 0x20
SDIR_ENTRY_SIZE = 0x20
SDIR_META_SIZE = 0x28


def clamp16(value):
    return -32768 if value < -32768 else 32767 if value > 32767 else value


def decode_frames(data, start, frame_count, coefs):
    """Return (pcm, headers) for frame_count 8-byte DSP-ADPCM frames."""
    pcm = []
    headers = []
    y1 = y2 = 0
    for frame in range(frame_count):
        position = start + frame * 8
        header = data[position]
        headers.append(header)
        scale = 1 << (header & 15)
        c1 = coefs[(header >> 4) * 2]
        c2 = coefs[(header >> 4) * 2 + 1]
        for i in range(14):
            byte = data[position + 1 + i // 2]
            nibble = (byte >> 4) if i % 2 == 0 else (byte & 15)
            if nibble >= 8:
                nibble -= 16
            sample = clamp16(((nibble * scale) << 11) + 1024 + c1 * y1 + c2 * y2 >> 11)
            pcm.append(sample)
            y2 = y1
            y1 = sample
    return pcm, headers


def encode_frames(pcm, headers, coefs, gain):
    """Re-encode gain-scaled pcm keeping each frame's predictor. Returns
    (bytes, decoded_pcm)."""
    out = bytearray()
    decoded = []
    y1 = y2 = 0
    for frame, old_header in enumerate(headers):
        predictor = old_header >> 4
        c1 = coefs[predictor * 2]
        c2 = coefs[predictor * 2 + 1]
        targets = [int(round(value * gain)) for value in pcm[frame * 14:frame * 14 + 14]]
        scale = max((old_header & 15) - 1, 0)
        while True:
            h1, h2 = y1, y2
            nibbles = []
            produced = []
            fits = True
            for target in targets:
                residual = (target << 11) - 1024 - (c1 * h1 + c2 * h2)
                nibble = (residual + (1024 << scale)) >> (11 + scale)
                if nibble < -8 or nibble > 7:
                    if scale < 12:
                        fits = False
                        break
                    nibble = -8 if nibble < -8 else 7
                sample = clamp16(((nibble << scale) << 11) + 1024 + c1 * h1 + c2 * h2 >> 11)
                nibbles.append(nibble & 15)
                produced.append(sample)
                h2 = h1
                h1 = sample
            if fits:
                break
            scale += 1
        y1, y2 = h1, h2
        decoded.extend(produced)
        out.append((predictor << 4) | scale)
        for i in range(0, 14, 2):
            out.append((nibbles[i] << 4) | nibbles[i + 1])
    return bytes(out), decoded


def scale_bank(archive, sdir_start, sdir_size, samp_start, samp_size, gain, label):
    """Scale every sample of one bank in place. Returns peak ratios."""
    position = sdir_start
    seen_meta = set()
    ratios = []
    count = 0
    while archive[position:position + 4] != b"\xFF\xFF\xFF\xFF":
        record = position
        position += SDIR_ENTRY_SIZE
        sample_id, = struct.unpack_from(">H", archive, record)
        offset, = struct.unpack_from(">I", archive, record + 4)
        samples, loop_start, loop_length, meta_offset = struct.unpack_from(">IIII", archive, record + 0x10)
        meta = sdir_start + meta_offset
        if meta in seen_meta:
            raise ValueError(f"{label}: sample {sample_id:04X} shares its metadata with another sample")
        seen_meta.add(meta)
        if offset + samples_to_bytes(samples) > samp_size:
            raise ValueError(f"{label}: sample {sample_id:04X} extends past its SAMP data")

        coefs = struct.unpack_from(">16h", archive, meta + 8)
        frame_count = (samples + 13) // 14
        start = samp_start + offset
        pcm, headers = decode_frames(archive, start, frame_count, coefs)

        if archive[meta + 2] != headers[0]:
            raise ValueError(f"{label}: sample {sample_id:04X} initial predictor/scale mismatch")
        if loop_length > 1:
            loop_frame = loop_start // 14
            if archive[meta + 3] != headers[loop_frame]:
                raise ValueError(f"{label}: sample {sample_id:04X} loop predictor/scale mismatch")
            if loop_start >= 2:
                lyn2, lyn1 = struct.unpack_from(">hh", archive, meta + 4)
                if (lyn2, lyn1) != (pcm[loop_start - 2], pcm[loop_start - 1]):
                    raise ValueError(f"{label}: sample {sample_id:04X} loop history mismatch")

        encoded, decoded = encode_frames(pcm, headers, coefs, gain)
        archive[start:start + len(encoded)] = encoded
        archive[meta + 2] = encoded[0]
        if loop_length > 1:
            archive[meta + 3] = encoded[(loop_start // 14) * 8]
            if loop_start >= 2:
                struct.pack_into(">hh", archive, meta + 4, decoded[loop_start - 2], decoded[loop_start - 1])

        old_peak = max(map(abs, pcm), default=0)
        new_peak = max(map(abs, decoded), default=0)
        if old_peak >= 2000:
            ratios.append(new_peak / old_peak)
        count += 1
    return count, ratios


def read_banks(archive):
    bank_table_offset, bank_table_size = struct.unpack_from(">II", archive, 0x20)
    group_chunk_offset, _ = struct.unpack_from(">II", archive, 0x38)
    sample_chunk_offset, _ = struct.unpack_from(">II", archive, 0x40)
    banks = {}
    for index in range(bank_table_size // BANK_ENTRY_SIZE):
        entry = bank_table_offset + index * BANK_ENTRY_SIZE
        bank_id, = struct.unpack_from(">H", archive, entry)
        group_offset, group_size, sample_offset, sample_size = struct.unpack_from(">IIII", archive, entry + 4)
        group_start = group_chunk_offset + group_offset
        sdir_offset, sequence_offset = struct.unpack_from(">II", archive, group_start + 8)
        banks[bank_id] = {
            "sdir_start": group_start + sdir_offset,
            "sdir_size": sequence_offset - sdir_offset,
            "samp_start": sample_chunk_offset + sample_offset,
            "samp_size": sample_size,
        }
    return banks


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Source MSM archive")
    parser.add_argument("--output", required=True, type=Path, help="New output MSM path (must not exist)")
    parser.add_argument("--gain", type=float, default=SFX_GAIN, help=f"Linear gain (default {SFX_GAIN})")
    parser.add_argument("--only", type=lambda v: int(v, 16), nargs="*", help="Only process these hex bank IDs (testing)")
    args = parser.parse_args(argv)

    if args.output.exists():
        print(f"Error: refusing to overwrite existing output: {args.output}", file=sys.stderr)
        return 1
    source = args.input.read_bytes()
    if source[:4] != b"GSND" or struct.unpack_from(">I", source, 8)[0] != len(source):
        print("Error: input is not a valid GSND/MSM archive", file=sys.stderr)
        return 1

    archive = bytearray(source)
    banks = read_banks(source)
    skipped = {bank_id: banks[bank_id] for bank_id in EXCLUDED_BANKS if bank_id in banks}
    todo = [bank_id for bank_id in sorted(banks)
            if bank_id not in EXCLUDED_BANKS and (args.only is None or bank_id in args.only)]

    def overlaps(a, b):
        return a["samp_start"] < b["samp_start"] + b["samp_size"] and b["samp_start"] < a["samp_start"] + a["samp_size"]

    for bank_id in todo:
        for other_id, other in banks.items():
            if other_id != bank_id and (other_id in skipped) and overlaps(banks[bank_id], other):
                print(f"Error: bank {bank_id:04X} shares sample data with excluded bank {other_id:04X}", file=sys.stderr)
                return 1

    all_ratios = []
    for bank_id in todo:
        bank = banks[bank_id]
        count, ratios = scale_bank(archive, bank["sdir_start"], bank["sdir_size"], bank["samp_start"],
                                   bank["samp_size"], args.gain, f"bank {bank_id:04X}")
        all_ratios.extend(ratios)
        print(f"Bank {bank_id:04X}: scaled {count} samples", flush=True)

    if len(archive) != len(source) or archive[:HEADER_SIZE] != source[:HEADER_SIZE]:
        raise AssertionError("Header or size changed")
    for bank_id, bank in skipped.items():
        for key_start, key_size in (("sdir_start", "sdir_size"), ("samp_start", "samp_size")):
            a, n = bank[key_start], bank[key_size]
            if archive[a:a + n] != source[a:a + n]:
                raise AssertionError(f"Excluded bank {bank_id:04X} changed")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("xb") as output:
        output.write(archive)
    print(f"Created {args.output}")
    if all_ratios:
        print(f"Peak ratio (samples with peak >= 2000): min {min(all_ratios):.3f}, "
              f"median {statistics.median(all_ratios):.3f}, max {max(all_ratios):.3f}")
    print("Excluded banks " + ", ".join(f"{b:04X}" for b in skipped) + " are byte-identical to the input.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
