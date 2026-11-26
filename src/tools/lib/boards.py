"""Board files (data/w0X.bin): the space (masu) table in file 0, its flags and kinds."""
import struct

from tools.lib import mpdata
from tools.lib.mpdata import lz_decode  # noqa: F401 (other modules import it from here)


def flag_offset(blob, space_id):
    pos = 4
    for index in range(struct.unpack_from(">I", blob, 0)[0]):
        links = struct.unpack_from(">H", blob, pos + 44)[0]
        if index + 1 == space_id:
            return pos + 38
        pos += 46 + 2 * links
    raise ValueError(space_id)


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
    blob = mpdata.read_file(data, offsets, 0)
    return bytearray(blob), start, end


def replace_file0(data, offsets, start, end, blob):
    packed = mpdata.pack_file(bytes(blob))
    delta = len(packed) - (end - start)
    out = data[:start] + packed + data[end:]
    new_offsets = [o + delta if o > start else o for o in offsets]
    out = struct.pack(">I", len(offsets)) + struct.pack(f">{len(offsets)}I", *new_offsets) + out[4 + 4 * len(offsets):]
    return out, new_offsets
