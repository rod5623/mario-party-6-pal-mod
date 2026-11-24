"""Dump the space (masu) table of a board archive: python -m tools.scripts.masu_dump w03 [w03n ...]

root/data/<board>.bin file 0 is LZ-compressed (decode type 1, HuDecodeLz in decode.c). Layout, as read by
fn_80174A3C: u32 count; then per space (ids are 1-based, id = index + 1):
  3 x f32 position, 3 x f32 (copied to +0x24), 3 x f32 scale, u16 type (-> masu+0x10),
  u32 flags (-> masu+0x14), u16 (-> masu+0x30), u16 link count n, n x u16 link indices (0-based; +1 = id).
Accessors: fn_80176F84 = type, fn_80176FCC = flags, fn_80176F54 = &masu (stride 0x70).
"""
import struct
import sys

from tools.lib import mpdata
from tools.lib.boards import lz_decode
from tools.lib.paths import GAME_DATA


def load(board, root=GAME_DATA):
    data, offsets = mpdata.read_archive(f"{root}/{board}.bin")
    start, end = mpdata.file_bounds(data, offsets, 0)
    size, kind = struct.unpack_from(">II", data, start)
    blob = lz_decode(data[start + 8:end], size) if kind == 1 else mpdata.read_file(data, offsets, 0)
    count = struct.unpack_from(">I", blob, 0)[0]
    pos, spaces = 4, []
    for index in range(count):
        position = struct.unpack_from(">3f", blob, pos)
        kind_, flags, extra, links = struct.unpack_from(">HIHH", blob, pos + 36)
        linked = struct.unpack_from(f">{links}H", blob, pos + 46)
        spaces.append({"id": index + 1, "pos": position, "type": kind_, "flags": flags,
                       "extra": extra, "links": [l + 1 for l in linked]})
        pos += 46 + 2 * links
    assert pos == len(blob)
    return spaces


if __name__ == "__main__":
    for board in sys.argv[1:] or ["w03"]:
        print(board)
        for s in load(board):
            print(s["id"], tuple(round(v) for v in s["pos"]), hex(s["type"]), hex(s["flags"]), s["links"])
