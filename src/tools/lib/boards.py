"""Board files (data/w0X.bin): the space (masu) table in file 0, its flags and kinds."""
import struct

from tools.lib import mpdata


def flag_offset(blob, space_id):
    pos = 4
    for index in range(struct.unpack_from(">I", blob, 0)[0]):
        links = struct.unpack_from(">H", blob, pos + 44)[0]
        if index + 1 == space_id:
            return pos + 38
        pos += 46 + 2 * links
    raise ValueError(space_id)


def lz_decode(src, size):
    buf = bytearray(1024)
    pos, flag, i, out = 958, 0, 0, bytearray()
    while len(out) < size:
        flag >>= 1
        if not flag & 0x100:
            flag = src[i] | 0xFF00
            i += 1
        if flag & 1:
            b = src[i]
            i += 1
            buf[pos] = b
            pos = (pos + 1) & 0x3FF
            out.append(b)
        else:
            a, c = src[i], src[i + 1]
            i += 2
            a |= (c & ~0x3F) << 2
            for j in range((c & 0x3F) + 3):
                b = buf[(a + j) & 0x3FF]
                buf[pos] = b
                pos = (pos + 1) & 0x3FF
                out.append(b)
    return bytes(out[:size])


def kind_offset(blob, space_id):
    pos = 4
    for index in range(struct.unpack_from(">I", blob, 0)[0]):
        links = struct.unpack_from(">H", blob, pos + 44)[0]
        if index + 1 == space_id:
            return pos + 42
        pos += 46 + 2 * links
    raise ValueError(space_id)


def load_spaces(data, offsets):
    start, end = mpdata.file_bounds(data, offsets, 0)
    size, kind = struct.unpack_from(">II", data, start)
    blob = lz_decode(data[start + 8:end], size) if kind == 1 else mpdata.read_file(data, offsets, 0)
    return bytearray(blob), start, end


def replace_file0(data, offsets, start, end, blob):
    packed = mpdata.pack_file(bytes(blob))
    delta = len(packed) - (end - start)
    out = data[:start] + packed + data[end:]
    new_offsets = [o + delta if o > start else o for o in offsets]
    out = struct.pack(">I", len(offsets)) + struct.pack(f">{len(offsets)}I", *new_offsets) + out[4 + 4 * len(offsets):]
    return out, new_offsets
